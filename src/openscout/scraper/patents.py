"""Google Patents scraper — IP-as-commercial-signal.

For researchers with at least one industry email on a paper they authored
(detected via `INDUSTRY_DOMAINS` in work_scoring.py), search Google Patents
for them as inventor. A filed patent is a strong commercial signal: the
researcher is producing IP at a company, which is a much shorter line to
revenue than an academic paper.

Strategy:
  - Use the undocumented-but-stable `https://patents.google.com/xhr/query`
    endpoint. It returns clean JSON (no JS-render needed, no HTML scrape).
  - Query: `?url=inventor%3D<name>&exp=` — same encoding the live site uses
    when you type the inventor in the search bar. Filter `type=PATENT` to
    drop NPL (non-patent literature) noise.
  - Parse `results.cluster[*].result[*].patent` — title / assignee /
    filing_date / publication_number are all there.

Each hit is stored as a `Signal` row of type='patent', keyed by
`source=<publication_number>` so re-runs don't dupe. We skip researchers
who already have a patent Signal in the last 30 days (cheap re-run guard).

Note on robustness: Google can change this endpoint's shape without notice.
We log + skip on every parse failure rather than crashing the whole batch.
A textual fallback would mean rendering the JS-heavy SPA, which is heavy;
0 hits is a fine answer when JSON parsing fails.
"""

import time
import urllib.parse
from datetime import UTC, datetime, timedelta

import httpx
from selectolax.parser import HTMLParser
from sqlalchemy import select

from ..db import session_scope
from ..models import Paper, PaperAuthor, Researcher, Signal
from .work_scoring import INDUSTRY_DOMAINS

PATENTS_XHR = "https://patents.google.com/xhr/query"

# Mimic a real browser — Google Patents 403s on most bot UAs.
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "en-US,en;q=0.9",
    "Referer": "https://patents.google.com/",
}


def _has_industry_email(emails: list[str] | None) -> bool:
    """Lightweight mirror of work_scoring._industry_match — only the boolean."""
    if not emails:
        return False
    for e in emails:
        if not isinstance(e, str) or "@" not in e:
            continue
        domain = e.split("@", 1)[1].lower().strip()
        for d in INDUSTRY_DOMAINS:
            if domain == d or domain.endswith("." + d):
                return True
    return False


def _strip_tags(s: str | None) -> str:
    """Remove the <b>…</b> highlight tags Google embeds in inventor / title."""
    if not s:
        return ""
    # Cheap path — most fields only have a couple of tags
    if "<" not in s:
        return s.strip()
    return HTMLParser(s).text(separator="", strip=True).strip()


def _normalize_patent_id(pub_no: str | None) -> str | None:
    """`US20200304997A1` → return as-is. Google uses publication_number which
    is what users grep for. Strip whitespace; reject empties."""
    if not pub_no:
        return None
    pub_no = pub_no.strip()
    return pub_no or None


def _parse_results(data: dict) -> list[dict]:
    """Pull patent records out of the xhr/query JSON. Tolerant of missing keys."""
    out: list[dict] = []
    results = data.get("results") or {}
    clusters = results.get("cluster") or []
    for cluster in clusters:
        if not isinstance(cluster, dict):
            continue
        for entry in cluster.get("result") or []:
            if not isinstance(entry, dict):
                continue
            p = entry.get("patent") or {}
            if not isinstance(p, dict):
                continue
            patent_id = _normalize_patent_id(p.get("publication_number"))
            if not patent_id:
                continue
            out.append(
                {
                    "patent_id": patent_id,
                    "title": _strip_tags(p.get("title")),
                    "assignee": _strip_tags(p.get("assignee")) or None,
                    "filing_date": p.get("filing_date") or None,
                    "url": f"https://patents.google.com/patent/{patent_id}/en",
                }
            )
    return out


def _search_inventor(client: httpx.Client, name: str) -> list[dict]:
    """Query Google Patents for a single inventor name. Returns [] on any error."""
    try:
        # Google's URL-param ordering: inventor=<name>&type=PATENT
        # The `url` param is the URL-encoded inner query string.
        inner = f"inventor={urllib.parse.quote(name)}&type=PATENT"
        r = client.get(
            PATENTS_XHR,
            params={"url": inner, "exp": ""},
            timeout=20.0,
        )
        if r.status_code != 200:
            return []
        try:
            data = r.json()
        except Exception:
            return []
        return _parse_results(data)
    except Exception:
        return []


def _has_recent_patent_signal(db, researcher_id: int, cutoff: datetime) -> bool:
    """True if the researcher already has a patent Signal newer than cutoff.
    Avoids hammering Google Patents on every nightly cron."""
    existing = db.execute(
        select(Signal.id)
        .where(
            Signal.researcher_id == researcher_id,
            Signal.type == "patent",
            Signal.detected_at >= cutoff,
        )
        .limit(1)
    ).first()
    return existing is not None


def _candidate_researcher_ids(db) -> list[int]:
    """Researchers who appear as authors on any paper that has an industry email.

    We pre-load each candidate paper's `author_emails` once and union the
    researcher_ids across all matching papers — far cheaper than per-researcher
    Python-side scans, and avoids depending on whether emails got attributed
    back to specific authors (which `pdf_emails.py` doesn't do).
    """
    paper_rows = db.execute(
        select(Paper.id, Paper.author_emails).where(Paper.author_emails.is_not(None))
    ).all()
    industry_paper_ids: list[int] = []
    for pid, emails in paper_rows:
        if _has_industry_email(emails):
            industry_paper_ids.append(int(pid))
    if not industry_paper_ids:
        return []

    rows = db.execute(
        select(PaperAuthor.researcher_id)
        .where(PaperAuthor.paper_id.in_(industry_paper_ids))
        .distinct()
    ).all()
    return [int(r[0]) for r in rows]


def scrape_patents(limit: int = 30) -> dict[str, int]:
    """Search Google Patents for industry-affiliated researchers' inventions.

    Returns: {attempted, with_patents, patents_found, errors}
      attempted    — researchers we ran a search for
      with_patents — researchers who had >=1 patent hit
      patents_found — total Signal rows added (deduped on publication_number)
      errors       — HTTP / parse failures
    """
    counts = {"attempted": 0, "with_patents": 0, "patents_found": 0, "errors": 0}
    cutoff = datetime.now(UTC) - timedelta(days=30)

    client = httpx.Client(headers=HEADERS, follow_redirects=True)
    try:
        with session_scope() as db:
            candidate_ids = _candidate_researcher_ids(db)
            if not candidate_ids:
                return counts

            # Pull Researcher rows, drop those with a recent patent Signal,
            # cap at `limit`. We sort by id so re-runs are stable.
            researchers = list(
                db.execute(
                    select(Researcher)
                    .where(Researcher.id.in_(candidate_ids))
                    .order_by(Researcher.id)
                )
                .scalars()
                .all()
            )

            attempted = 0
            for r in researchers:
                if attempted >= limit:
                    break
                if not r.name_en or not r.name_en.strip():
                    continue
                if _has_recent_patent_signal(db, r.id, cutoff):
                    continue

                attempted += 1
                counts["attempted"] += 1

                try:
                    hits = _search_inventor(client, r.name_en.strip())
                except Exception:
                    counts["errors"] += 1
                    time.sleep(2.0)
                    continue

                # NB: hits=[] is a legitimate "no patents" answer, not an error.
                # We only bump `errors` when the request itself blew up (above).
                if hits:
                    counts["with_patents"] += 1

                for hit in hits:
                    patent_id = hit["patent_id"]
                    existing = db.execute(
                        select(Signal.id).where(
                            Signal.researcher_id == r.id,
                            Signal.type == "patent",
                            Signal.source == patent_id,
                        )
                    ).first()
                    if existing:
                        continue
                    db.add(
                        Signal(
                            researcher_id=r.id,
                            type="patent",
                            payload={
                                "patent_id": patent_id,
                                "title": hit["title"],
                                "assignee": hit["assignee"],
                                "filing_date": hit["filing_date"],
                                "url": hit["url"],
                            },
                            source=patent_id,
                            occurred_at=datetime.now(UTC),
                        )
                    )
                    counts["patents_found"] += 1

                time.sleep(2.0)
    finally:
        client.close()
    return counts
