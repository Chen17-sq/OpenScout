"""Awards scraper — prestigious early-career awards as "rising star" signals.

The investor's strongest qualitative filter is *peer recognition*. A name on the
ACM Doctoral Dissertation list, Packard, Sloan, or TR35 list is the cheapest
signal we have that a researcher's senior peers already think they're a winner.

Each recipient match (fuzzy on `Researcher.name_en`) becomes a `Signal` with
`type="award"`. The `_signal_tag` pass in `deep_dive.py` later folds these into
the visible "rising star" chip — we just record the raw signals here.

Source matrix:

  ACM Doctoral Diss.   Wikipedia  · `action=parse` API · single wikitable
  Sloan Research Fwsh. Wikipedia  · only Nobel-laureate fellows (~66) — limited but
                                    a strong overlap signal when it hits
  Packard Fellowship   packard.org · wp-json/wp/v2/fellow · 700+ records (full directory)
  MIT TR35             technologyreview.com · per-year category list pages, parsed for
                                    h3 names. We hit ai-YYYY and robotics-YYYY for
                                    2020-2025 (the only years that matter for our cohort).

Skipped (in v1):
  - NSF CAREER  — endpoint is per-award, not per-cohort; need RSS or bulk search
  - Forbes 30u30 — JS-rendered, no inline JSON for names
  - NSFC 优青   — no English page; PDF lists only

Design notes:

  - Each source is in its own helper that returns a list of `(name, year, source_url,
    description)` tuples. The top-level orchestrator handles all DB writes + signal
    deduplication, so a per-source failure just drops one source — not the whole run.
  - Name matching is exact-on-normalize for v1. Fuzzy (Levenshtein, surname-initial
    expansion) is left for v2 to avoid false positives polluting Signal history.
  - Idempotent: we key dedup on (researcher_id, "award", source_url) so re-running
    the scraper does not double-write signals.
"""

from __future__ import annotations

import re
import time
from datetime import UTC, datetime

import httpx
from selectolax.parser import HTMLParser
from sqlalchemy import select

from ..db import session_scope
from ..models import Researcher, Signal

# Wikipedia is rate-limit-strict on Mozilla UAs but generous if you identify a contact.
WIKI_UA = "OpenScout/0.7 researcher-tracker (https://github.com/Chen17-sq/OpenScout)"
# Most other sites Cloudflare-block bot-y UAs; a real Chrome string works for them.
BROWSER_UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0.0.0 Safari/537.36"
)
WIKI_API = "https://en.wikipedia.org/w/api.php"

# Years we actually care about. Older recipients are now senior PIs and already
# in our anchor graph; the freshness gradient matters more than completeness.
TR35_MIN_YEAR = 2018
TR35_MAX_YEAR = datetime.now(UTC).year
# TR35 splits each year into category pages; we only want the AI / robotics ones.
TR35_CATEGORIES = ("artificial-intelligence", "robotics", "computing")


# ── Name normalization for fuzzy matching ──────────────────────────────────────


def _normalize_name(s: str) -> str:
    """Collapse whitespace and lowercase. Strips Wikipedia footnote markers."""
    s = re.sub(r"\[[\w\s,]+\]", "", s or "")  # [4], [n 1], [note] all gone
    # Hair space and NBSP show up in Wikipedia HTML; normalize to plain space
    s = s.replace(" ", " ").replace(" ", " ").replace(" ", " ")
    return " ".join(s.strip().lower().split())


def _clean_name(s: str) -> str:
    """Display-friendly name (case preserved, footnotes stripped)."""
    s = re.sub(r"\[[\w\s,]+\]", "", s or "")
    s = s.replace(" ", " ").replace(" ", " ").replace(" ", " ")
    return " ".join(s.strip().split())


# ── Wikipedia helper ───────────────────────────────────────────────────────────


def _wiki_parse_html(client: httpx.Client, page: str) -> str | None:
    """Fetch the parsed HTML body for a Wikipedia page via the action API."""
    try:
        r = client.get(
            WIKI_API,
            params={
                "action": "parse",
                "page": page,
                "format": "json",
                "prop": "text",
                "redirects": "1",
            },
            headers={"User-Agent": WIKI_UA},
            timeout=20.0,
        )
        if r.status_code != 200:
            return None
        data = r.json()
        return (data.get("parse") or {}).get("text", {}).get("*")
    except Exception:
        return None


# ── Source 1: ACM Doctoral Dissertation Award ─────────────────────────────────


def _fetch_acm_doctoral(client: httpx.Client) -> list[tuple[str, str | None, str, str]]:
    """ACM Doctoral Dissertation — the most prestigious CS thesis award.

    Returns (name, year, source_url, description). Year may be None if a row
    is in a rowspan group we couldn't parse cleanly.
    """
    html = _wiki_parse_html(client, "ACM_Doctoral_Dissertation_Award")
    if not html:
        return []

    out: list[tuple[str, str | None, str, str]] = []
    tree = HTMLParser(html)
    table = tree.css_first("table.wikitable")
    if not table:
        return []

    source_url = "https://en.wikipedia.org/wiki/ACM_Doctoral_Dissertation_Award"
    year: str | None = None
    for row in table.css("tr")[1:]:
        cells = row.css("td, th")
        cell_texts = [c.text().strip() for c in cells]
        if not cell_texts:
            continue

        first = cell_texts[0]
        # Year cells are 4-digit ints, possibly with rowspan grouping winner + mentions
        if first.isdigit() and 1900 < int(first) < 2100:
            year = first
            cells_after = cell_texts[1:]
        else:
            cells_after = cell_texts

        # First non-empty post-year cell is the recipient
        for raw in cells_after:
            name = _clean_name(raw)
            if name and len(name) > 2 and not name.isdigit():
                out.append(
                    (
                        name,
                        year,
                        source_url,
                        "ACM Doctoral Dissertation Award",
                    )
                )
                break  # one recipient per cell-block
    return out


# ── Source 2: Sloan Research Fellowship (Wikipedia) ───────────────────────────


def _fetch_sloan(client: httpx.Client) -> list[tuple[str, str | None, str, str]]:
    """Sloan Research Fellowship — partial coverage (Nobel-laureate fellows only).

    Wikipedia only maintains the laureate subset, but those that *do* appear are
    high-prestige overlaps with our anchor graph. The full Sloan database is
    Cloudflare-blocked; if/when we have a key-based fetcher we'll replace this.
    """
    html = _wiki_parse_html(client, "Sloan_Research_Fellowship")
    if not html:
        return []

    out: list[tuple[str, str | None, str, str]] = []
    tree = HTMLParser(html)
    tables = tree.css("table.wikitable")
    if len(tables) < 2:
        return []

    source_url = "https://en.wikipedia.org/wiki/Sloan_Research_Fellowship"
    # Table 1 is the named list: Name | Field | Sloan year | Prize year
    for row in tables[1].css("tr")[1:]:
        cells = [c.text().strip() for c in row.css("td")]
        if len(cells) < 3:
            continue
        name = _clean_name(cells[0])
        year = cells[2] if cells[2].isdigit() else None
        field = cells[1] if len(cells) > 1 else ""
        if name and len(name) > 2:
            out.append(
                (
                    name,
                    year,
                    source_url,
                    f"Sloan Research Fellowship · {field}".strip(" ·"),
                )
            )
    return out


# ── Source 3: Packard Fellowships (wp-json) ───────────────────────────────────


def _fetch_packard(client: httpx.Client) -> list[tuple[str, str | None, str, str]]:
    """Packard Fellowships for Science and Engineering — full directory via wp-json.

    The wp-json endpoint exposes ~700 records across all years. No explicit year
    field, but `date` (post publish date) reliably tracks the cohort year for
    recent fellows.
    """
    out: list[tuple[str, str | None, str, str]] = []
    base = "https://www.packard.org/wp-json/wp/v2/fellow"
    headers = {"User-Agent": BROWSER_UA, "Accept": "application/json"}

    # Probe page 1 to learn page count, then iterate.
    try:
        r = client.get(
            base,
            params={"per_page": 100, "page": 1, "_fields": "title,date,link,slug"},
            headers=headers,
            timeout=25.0,
        )
        if r.status_code != 200:
            return []
        total_pages = int(r.headers.get("X-WP-TotalPages") or "1")
    except Exception:
        return []

    def _process(rows: list[dict]) -> None:
        for d in rows:
            title = (d.get("title") or {}).get("rendered") or ""
            # WordPress renders HTML entities (e.g. M&#038;)
            title = title.replace("&#038;", "&").replace("&amp;", "&")
            link = d.get("link") or "https://www.packard.org/fellow/"
            date_iso = d.get("date") or ""
            year = date_iso.split("-", 1)[0] if date_iso else None
            name = _clean_name(title)
            if name and len(name) > 2:
                out.append((name, year, link, "Packard Fellowship for Science & Engineering"))

    try:
        _process(r.json())
    except Exception:
        return []

    # Be polite; 8 pages × 0.3s is fine.
    for page in range(2, total_pages + 1):
        try:
            r = client.get(
                base,
                params={
                    "per_page": 100,
                    "page": page,
                    "_fields": "title,date,link,slug",
                },
                headers=headers,
                timeout=25.0,
            )
            if r.status_code != 200:
                continue
            _process(r.json())
            time.sleep(0.3)
        except Exception:
            continue
    return out


# ── Source 4: MIT Technology Review TR35 ──────────────────────────────────────


def _fetch_tr35(client: httpx.Client) -> list[tuple[str, str | None, str, str]]:
    """TR35 Innovators Under 35 — per-year per-category list pages.

    URLs follow `…/innovators-under-35/<category>-<year>/`. We restrict to
    AI / robotics / computing for the years we care about. Names live in `<h3>`
    nodes — the page also contains other h3s ("Categories", "Past Years",
    "Share") that we filter out.
    """
    out: list[tuple[str, str | None, str, str]] = []
    headers = {"User-Agent": BROWSER_UA}
    skip_h3 = {"categories", "past years", "share", "related story", "full list"}

    for year in range(TR35_MIN_YEAR, TR35_MAX_YEAR + 1):
        for category in TR35_CATEGORIES:
            url = f"https://www.technologyreview.com/innovators-under-35/{category}-{year}/"
            try:
                r = client.get(url, headers=headers, timeout=25.0, follow_redirects=True)
            except Exception:
                continue
            if r.status_code != 200:
                continue
            tree = HTMLParser(r.text)
            for h3 in tree.css("h3"):
                txt = (h3.text() or "").strip()
                if not txt or len(txt) > 60:
                    continue
                if txt.lower() in skip_h3:
                    continue
                # h3 text that's not a person ("by ...", credit lines)
                if txt.lower().startswith("by ") or "©" in txt:
                    continue
                # Names typically have at least one space (first + last)
                if " " not in txt:
                    continue
                # No digits — kills "30 Under 30", "Issue 8" titles
                if any(ch.isdigit() for ch in txt):
                    continue
                name = _clean_name(txt)
                if name and len(name) > 2:
                    pretty = category.replace("-", " ").title()
                    out.append(
                        (
                            name,
                            str(year),
                            url,
                            f"MIT TR35 Innovators Under 35 · {pretty}",
                        )
                    )
            time.sleep(0.6)
    return out


# ── Main ───────────────────────────────────────────────────────────────────────


def _researcher_index(db) -> dict[str, list[Researcher]]:
    """Build a lowercase-name → [Researcher] map for fast matching.

    Multi-keyed by normalized name; collisions are rare but a single normalized
    name can map to multiple distinct people (e.g. two "John Wang"s). We
    intentionally only emit signals for unambiguous matches to avoid contaminating
    the wrong researcher's signal feed.
    """
    idx: dict[str, list[Researcher]] = {}
    rs = db.execute(select(Researcher)).scalars().all()
    for r in rs:
        for nm in (r.name_en, r.name_zh):
            if not nm:
                continue
            key = _normalize_name(nm)
            if not key:
                continue
            idx.setdefault(key, []).append(r)
    return idx


def scrape_awards() -> dict[str, int]:
    """Scrape recipient lists from prestige awards and emit Signal rows.

    Returns a counts dict with keys:
        sources_scraped     — how many sources came back with at least 1 recipient
        recipients_seen     — total (name, year) tuples harvested
        matched_researchers — # of UNIQUE researchers we created signals for
        errors              — internal exception count (orchestrator-level)
    """
    counts = {
        "sources_scraped": 0,
        "recipients_seen": 0,
        "matched_researchers": 0,
        "errors": 0,
        "signals_added": 0,
    }

    sources: list[tuple[str, callable]] = [
        ("acm_doctoral_dissertation", _fetch_acm_doctoral),
        ("sloan_research_fellowship", _fetch_sloan),
        ("packard_fellowship", _fetch_packard),
        ("mit_tr35", _fetch_tr35),
    ]

    client = httpx.Client(follow_redirects=True)
    matched: set[int] = set()

    try:
        # 1. Harvest recipients from every source. Any source that fails just
        #    contributes zero rows — we never let one bad source kill the run.
        all_recipients: list[tuple[str, str, str | None, str, str]] = []
        for source_name, fn in sources:
            try:
                items = fn(client)
                if items:
                    counts["sources_scraped"] += 1
                    for name, year, url, desc in items:
                        all_recipients.append((source_name, name, year, url, desc))
            except Exception:
                counts["errors"] += 1
                continue

        counts["recipients_seen"] = len(all_recipients)

        # 2. Match harvested names against the researchers table and emit signals.
        with session_scope() as db:
            idx = _researcher_index(db)
            for source_name, name, year, url, desc in all_recipients:
                key = _normalize_name(name)
                candidates = idx.get(key, [])
                # Skip ambiguous matches (>1 researcher with the same normalized
                # name) — we'd rather miss than misattribute.
                if len(candidates) != 1:
                    continue
                r = candidates[0]
                # Dedup on (researcher_id, type=award, source=source_url)
                existing = db.execute(
                    select(Signal).where(
                        Signal.researcher_id == r.id,
                        Signal.type == "award",
                        Signal.source == url,
                    )
                ).scalar_one_or_none()
                if existing:
                    continue
                try:
                    occurred_at = datetime(int(year), 6, 1, tzinfo=UTC) if year else None
                except (TypeError, ValueError):
                    occurred_at = None
                db.add(
                    Signal(
                        researcher_id=r.id,
                        type="award",
                        payload={
                            "award": source_name,
                            "year": year,
                            "source_url": url,
                            "description": desc,
                            "recipient_name": name,
                        },
                        source=url,
                        occurred_at=occurred_at,
                    )
                )
                counts["signals_added"] += 1
                matched.add(r.id)
    finally:
        client.close()

    counts["matched_researchers"] = len(matched)
    return counts
