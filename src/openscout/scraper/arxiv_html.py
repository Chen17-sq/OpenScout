"""arXiv HTML scraper — replaces PDF for email extraction.

arXiv now renders papers as HTML at https://arxiv.org/html/<id> (their own
native renderer; older papers fall back to ar5iv.labs.arxiv.org). This is
**much lighter** than PDF parsing:

  PDF:  500KB – 2MB · pypdf, slow + brittle on math-heavy docs
  HTML: 50 – 200KB · selectolax, milliseconds, structured DOM

We extract:
  - All emails on the first ~6000 chars (author block lives near the top)
  - Author affiliation strings (h2/h3 sections)
  - GitHub URLs (sometimes in the abstract that PDF misses)

Falls back to ar5iv.labs.arxiv.org/abs/<id> when arxiv.org/html/<id> 404s.
"""

import re
import time

import httpx
from selectolax.parser import HTMLParser
from sqlalchemy import desc, select

from ..db import session_scope
from ..models import Paper

EMAIL_RE = re.compile(
    r"[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}",
    re.UNICODE,
)
GITHUB_RE = re.compile(
    r"https?://(?:www\.)?github\.com/[\w.\-]+/[\w.\-]+",
    re.IGNORECASE,
)

HEADERS = {
    "User-Agent": "OpenScout/0.7 (+https://github.com/Chen17-sq/OpenScout)",
    "Accept": "text/html,application/xhtml+xml",
}


def _fetch_html(client: httpx.Client, arxiv_id: str) -> str | None:
    """Try arXiv native HTML first, then ar5iv mirror."""
    for url in (
        f"https://arxiv.org/html/{arxiv_id}v1",
        f"https://arxiv.org/html/{arxiv_id}",
        f"https://ar5iv.labs.arxiv.org/html/{arxiv_id}",
    ):
        try:
            r = client.get(url, timeout=20.0, follow_redirects=True)
            if r.status_code == 200 and "text/html" in r.headers.get("content-type", ""):
                return r.text
        except Exception:
            continue
    return None


def _clean_emails(matches: list[str]) -> list[str]:
    out: set[str] = set()
    for raw in matches:
        e = raw.rstrip(".,;:)").lower()
        if e.endswith(".png") or e.endswith(".pdf") or e.endswith(".jpg"):
            continue
        if "..." in e:
            continue
        if e in {"example@example.com", "info@example.com", "noreply@arxiv.org"}:
            continue
        out.add(e)
    return sorted(out)


def _extract_from_html(html: str) -> tuple[list[str], str | None]:
    """Parse first-page-ish region for emails + github url."""
    if not html:
        return [], None

    # Use selectolax for speed; the first .ltx_authors block (or first 6000 chars
    # of body text) is enough for the author footer.
    tree = HTMLParser(html)

    # Try selectolax author-area extraction first
    candidate_text_parts: list[str] = []
    for selector in (".ltx_authors", ".ltx_personname", "header", "div.author"):
        for node in tree.css(selector)[:3]:
            candidate_text_parts.append(node.text() or "")

    # Fallback: first big chunk of plaintext
    if not candidate_text_parts:
        full = tree.body.text(separator=" ") if tree.body else ""
        candidate_text_parts = [full[:8000]]

    blob = " ".join(candidate_text_parts)
    raw_emails = EMAIL_RE.findall(blob)
    emails = _clean_emails(raw_emails)

    # GitHub url — search broader body too
    full_text = tree.body.text(separator=" ") if tree.body else blob
    gh = None
    for m in GITHUB_RE.finditer(full_text):
        url = m.group(0).rstrip(".,);:")
        if "github.com/static" in url or "github.com/topics" in url:
            continue
        gh = url
        break

    return emails, gh


def scrape_papers(limit: int = 30, sleep_between: float = 1.2) -> dict[str, int]:
    """Walk papers with arxiv_id but no author_emails / code_url; fill both."""
    counts = {"attempted": 0, "with_emails": 0, "with_code": 0, "errors": 0, "no_html": 0}

    client = httpx.Client(headers=HEADERS, follow_redirects=True)
    try:
        with session_scope() as db:
            papers = list(
                db.execute(
                    select(Paper)
                    .where(
                        Paper.arxiv_id.is_not(None),
                        Paper.arxiv_id.notlike("or-%"),  # skip OpenReview synthetic ids
                        Paper.author_emails.is_(None),
                    )
                    .order_by(desc(Paper.first_seen_at))
                    .limit(limit)
                )
                .scalars()
                .all()
            )
            for paper in papers:
                counts["attempted"] += 1
                html = _fetch_html(client, paper.arxiv_id)
                if not html:
                    counts["no_html"] += 1
                    paper.author_emails = []  # mark attempted
                    time.sleep(sleep_between)
                    continue
                try:
                    emails, gh = _extract_from_html(html)
                    paper.author_emails = emails
                    if emails:
                        counts["with_emails"] += 1
                    if gh and not paper.code_url:
                        paper.code_url = gh
                        counts["with_code"] += 1
                except Exception:
                    counts["errors"] += 1
                    paper.author_emails = []
                time.sleep(sleep_between)
    finally:
        client.close()
    return counts
