"""Faculty-page scraper — surface researchers who quietly transitioned to AP.

Each spring, top CS departments update their faculty directory with the next
year's incoming assistant professors. Those names are the *exact* sweet spot
for our investor user: a PhD they may have been tracking has just become a
faculty lead at MIT / Stanford / Tsinghua / etc.

Approach (defensive + dual signal):

  1. Scrape each university's faculty directory page. URLs and selectors are
     fragile by definition — wrap each page in try/except and just log the
     skip when a selector returns 0 names. The next run will catch up when
     the structure stabilises.
  2. Persist the set of names seen at each university to
     `data/faculty_cache/<inst_slug>.json`. On subsequent runs, names that
     appear NEW vs the previous snapshot are strong "just-hired" candidates.
  3. Independent fuzzy-match pass: for ANY name extracted (new-cache hit or
     not), look up Researchers whose current_role IN ('phd','postdoc') and
     whose name_en normalises to the same string. Those are the ones we
     promote to incoming_ap — being on a faculty page when you were last
     known as a PhD is essentially a hiring announcement.

For each promoted researcher:
  - r.current_role = "incoming_ap"
  - r.role_source = "faculty_page"
  - add Signal(type="faculty_announcement", payload={institution, source_url,
    profile_url, detected_at, was_new_to_cache: bool})

NOTE: university IT changes URLs often and selectors silently break. We
tolerate this — counts["errors"] tracks which pages failed and the brief
should surface that signal so the maintainer can patch a selector.
"""

from __future__ import annotations

import json
import re
import time
from datetime import UTC, datetime
from pathlib import Path

import httpx
from selectolax.parser import HTMLParser
from sqlalchemy import select

from ..db import session_scope
from ..models import Researcher, Signal

HEADERS = {
    "User-Agent": "OpenScout/1.7 (+https://github.com/Chen17-sq/OpenScout)",
    "Accept": "text/html,application/xhtml+xml",
    "Accept-Language": "en-US,en;q=0.9,zh;q=0.7",
}

# Cache dir — created on first run. Gitignored (data/ in .gitignore).
CACHE_DIR = Path(__file__).resolve().parents[3] / "data" / "faculty_cache"


# Each entry: (slug, display_name, url, css_selector_for_link, optional name-attr).
# The selector pulls anchor tags that wrap a faculty card / row title. We
# extract .text() for the name and `href` for the profile URL.
#
# These selectors are best-guess based on inspection-friendly patterns. They
# WILL break — that's why every fetch is wrapped and errors are counted, not
# raised. When a selector starts returning 0 nodes, the maintainer should
# inspect the page and update the entry below.
UNIVERSITIES: list[dict[str, str]] = [
    {
        "slug": "mit_eecs",
        "name": "MIT EECS",
        "url": "https://www.eecs.mit.edu/people/",
        # MIT EECS — verified May 2026: faculty cards render names in <h5>.
        "selector": "h5",
    },
    {
        "slug": "stanford_cs",
        "name": "Stanford CS",
        "url": "https://cs.stanford.edu/faculty",
        # Stanford appears JS-rendered — leaving best-guess; will likely fail.
        # Maintainer task: revisit with playwright or find the JSON endpoint.
        "selector": ".views-row a, .directory-list a, td a, h3 a",
    },
    {
        "slug": "cmu_scs",
        "name": "CMU SCS",
        "url": "https://www.cs.cmu.edu/directory/faculty",
        # CMU SCS — verified May 2026: name links live in `a` tags on a flat directory page.
        # Filter happens via _clean_name (drops anything that isn't a 2-token English name).
        "selector": "a",
    },
    {
        "slug": "berkeley_eecs",
        "name": "Berkeley EECS",
        "url": "https://www2.eecs.berkeley.edu/Faculty/Lists/faculty.html",
        # Berkeley — verified May 2026: faculty names in <h3 a>.
        "selector": "h3 a",
    },
    {
        "slug": "princeton_cs",
        "name": "Princeton CS",
        "url": "https://www.cs.princeton.edu/people/faculty",
        # Princeton — verified May 2026: each faculty is an <h3 a>.
        "selector": "h3 a",
    },
    {
        "slug": "uw_cse",
        "name": "UW CSE",
        "url": "https://www.cs.washington.edu/people/faculty",
        # UW — verified May 2026: Elementor page builder puts names in
        # <p class=elementor-heading-title>. NOT anchors, so profile URL is None.
        "selector": "p.elementor-heading-title",
    },
    {
        "slug": "cornell_cs",
        "name": "Cornell CS",
        "url": "https://www.cs.cornell.edu/people/faculty",
        # Cornell — verified May 2026: `<div class=name>` wraps each faculty name.
        "selector": "div.name",
    },
    {
        "slug": "tsinghua_cs",
        "name": "清华大学计算机系",
        # NOTE: May 2026 — confirmed 404 on the canonical info/1099.htm page; the
        # Tsinghua CS faculty page moved. We keep the entry so it appears in error
        # counts and a maintainer can patch the URL.
        "url": "https://www.cs.tsinghua.edu.cn/info/1099.htm",
        "selector": "ul li a, .v_news_content a, .list a",
    },
    {
        "slug": "pku_cs",
        "name": "北京大学 CS",
        # NOTE: May 2026 — confirmed 404. URL needs to be updated.
        "url": "https://cs.pku.edu.cn/szdw1.htm",
        "selector": "ul li a, .Newslist a, .col_news_con a",
    },
    {
        "slug": "thu_iiis",
        "name": "清华大学交叉信息院",
        "url": "https://iiis.tsinghua.edu.cn/zh/list/show/30.html",
        "selector": "ul li a, .news_list a",
    },
]


# ── name extraction helpers ────────────────────────────────────────────────


# Trim academic titles, suffixes, departments — anything that isn't the name itself.
_TITLE_RE = re.compile(
    r"\b("
    r"prof(\.|essor)?|dr\.?|phd|ph\.d\.?|m\.?d\.?|"
    r"assistant|associate|adjunct|emeritus|emerita|"
    r"lecturer|instructor|visiting|chair|dean|director|fellow"
    r")\b",
    re.IGNORECASE,
)
_PARENS_RE = re.compile(r"[(（].*?[)）]")
_WS_RE = re.compile(r"\s+")
_PUNCT_TAIL_RE = re.compile(r"[\s,;:|\-–—.]+$")


def _clean_name(raw: str) -> str:
    """Strip whitespace, parenthetical asides, academic titles. Return name or ''."""
    if not raw:
        return ""
    s = raw.strip()
    # Drop "(Department of X)" / "（教授）" style annotations
    s = _PARENS_RE.sub(" ", s)
    # Drop common titles in EN
    s = _TITLE_RE.sub(" ", s)
    # Drop CJK common titles
    for t in ("教授", "副教授", "助理教授", "讲师", "研究员", "副研究员", "博士"):
        s = s.replace(t, " ")
    s = _WS_RE.sub(" ", s).strip()
    s = _PUNCT_TAIL_RE.sub("", s).strip()
    # Heuristic: a real human name is 2-6 tokens, mostly alpha (or CJK), 2-60 chars.
    if not s:
        return ""
    if len(s) < 2 or len(s) > 60:
        return ""
    # English-name pattern: at least two whitespace-separated tokens, mostly letters
    # OR a 2-4 char CJK string.
    tokens = s.split()
    if len(tokens) >= 2 and all(re.match(r"^[A-Za-z][A-Za-z\-'.]*$", t) for t in tokens):
        return s
    # Pure CJK name (2-4 chars, no spaces, all CJK)
    if 2 <= len(s) <= 5 and re.match(r"^[一-鿿]+$", s):
        return s
    return ""


def _normalize_for_match(name: str) -> str:
    """Canonical form for fuzzy matching against Researcher.name_en.

    Lowercases, strips middle initials, collapses whitespace. We deliberately
    DON'T try to handle "Family Given" vs "Given Family" reordering — the
    Researcher table stores names in English-style "Given Family" so the
    faculty page should match if the source uses the same convention.
    Surname/given mismatches will simply not be promoted, which is the safer
    failure mode for an investor-facing dashboard.
    """
    if not name:
        return ""
    s = name.strip().lower()
    # Remove middle initials like " J. " → " "
    s = re.sub(r"\b[a-z]\.\s*", " ", s)
    # Strip remaining periods, commas
    s = re.sub(r"[.,]", " ", s)
    s = _WS_RE.sub(" ", s).strip()
    return s


# ── HTTP + parse ────────────────────────────────────────────────────────────


# Sentinel: page answered HTTP 200 but the body was too small to be a real
# directory page (JS-only shell, stub error page). Distinct from None (HTTP /
# network error) so the caller can count `skipped_small` separately from
# `errors`.
SMALL_PAGE = object()


def _fetch_html(client: httpx.Client, url: str) -> str | None | object:
    """GET the page. Returns the HTML text, the SMALL_PAGE sentinel for a
    tiny 200-OK body, or None on HTTP / network error. Never raises."""
    try:
        r = client.get(url, timeout=20.0, follow_redirects=True)
    except (httpx.HTTPError, httpx.InvalidURL):
        return None
    if r.status_code != 200:
        return None
    # Some Chinese university servers serve GBK; httpx defaults to declared charset.
    if not r.text or len(r.text) < 200:
        return SMALL_PAGE
    return r.text


def _extract_names(html: str, selector: str, base_url: str) -> list[tuple[str, str | None]]:
    """Return list of (cleaned_name, profile_url_or_None).

    Robust to selectors that return zero nodes — we just yield no names and
    the caller treats it as "page structure changed."
    """
    try:
        tree = HTMLParser(html)
    except Exception:
        return []

    seen: set[str] = set()
    out: list[tuple[str, str | None]] = []
    for node in tree.css(selector):
        text = node.text(deep=True, separator=" ", strip=True)
        cleaned = _clean_name(text)
        if not cleaned:
            continue
        key = cleaned.lower()
        if key in seen:
            continue
        seen.add(key)
        # Profile URL — check node itself, then a descendant <a>, then closest
        # ancestor <a>. Many faculty layouts wrap the name span/heading in a
        # link to the profile page, but not always.
        href = node.attributes.get("href")
        if not href:
            for desc in node.css("a"):
                h = desc.attributes.get("href")
                if h:
                    href = h
                    break
        if not href:
            anc = node.parent
            for _ in range(4):
                if anc is None:
                    break
                if anc.tag == "a" and anc.attributes.get("href"):
                    href = anc.attributes.get("href")
                    break
                anc = anc.parent
        if href and href.startswith("/"):
            # resolve relative → absolute
            try:
                from urllib.parse import urljoin

                href = urljoin(base_url, href)
            except Exception:
                pass
        out.append((cleaned, href or None))
    return out


# ── cache I/O ──────────────────────────────────────────────────────────────


def _cache_path(slug: str) -> Path:
    return CACHE_DIR / f"{slug}.json"


def _load_cache(slug: str) -> set[str]:
    p = _cache_path(slug)
    if not p.exists():
        return set()
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
        return set(data.get("names", []))
    except (OSError, json.JSONDecodeError):
        return set()


def _save_cache(slug: str, names: list[str], url: str) -> None:
    try:
        CACHE_DIR.mkdir(parents=True, exist_ok=True)
        _cache_path(slug).write_text(
            json.dumps(
                {
                    "url": url,
                    "saved_at": datetime.now(UTC).isoformat(),
                    "names": sorted(names),
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )
    except OSError:
        # Cache write failure is non-fatal; we'll just lose the snapshot for this run.
        pass


# ── researcher matching + promotion ────────────────────────────────────────


def _match_and_promote(
    db,
    name: str,
    *,
    institution_name: str,
    source_url: str,
    profile_url: str | None,
    was_new_to_cache: bool,
) -> bool:
    """If `name` matches a Researcher with role phd/postdoc, promote and signal.

    Returns True if a promotion happened. Idempotent on already-incoming_ap.
    """
    target = _normalize_for_match(name)
    if not target:
        return False

    # Cheap LIKE pre-filter then exact normalize-compare in Python. The
    # alternative — full-table scan — gets expensive once researchers count
    # hits 10k+, and we run this against potentially hundreds of names.
    first_token = target.split(" ", 1)[0]
    if len(first_token) < 2:
        return False

    # Match against name_en OR name_zh (CJK names need direct compare)
    candidates = list(
        db.execute(select(Researcher).where(Researcher.name_en.ilike(f"%{first_token}%")))
        .scalars()
        .all()
    )
    # CJK pages give CJK names — try name_zh too
    if re.match(r"^[一-鿿]+$", name):
        zh_candidates = list(
            db.execute(select(Researcher).where(Researcher.name_zh == name)).scalars().all()
        )
        # de-dup
        ids = {c.id for c in candidates}
        for c in zh_candidates:
            if c.id not in ids:
                candidates.append(c)

    matched: Researcher | None = None
    for r in candidates:
        if _normalize_for_match(r.name_en) == target:
            matched = r
            break
        if r.name_zh and r.name_zh == name:
            matched = r
            break

    if not matched:
        return False

    # Only promote PhDs/postdocs — anchors / known APs already correct.
    # If current_role is null, we promote too: an unknown-role researcher
    # appearing on a faculty page is informative either way.
    if matched.current_role not in (None, "phd", "postdoc"):
        return False

    promoted = matched.current_role != "incoming_ap"
    if promoted:
        matched.current_role = "incoming_ap"
        matched.role_source = "faculty_page"

    # Always emit the signal — even if already incoming_ap, the appearance on a
    # NEW university page is itself news (e.g. switched offer). De-dup is done
    # by occurred_at + payload comparison; we keep it simple here and rely on
    # consumers not over-counting.
    db.add(
        Signal(
            researcher_id=matched.id,
            type="faculty_announcement",
            payload={
                "institution": institution_name,
                "source_url": source_url,
                "profile_url": profile_url,
                "detected_at": datetime.now(UTC).isoformat(),
                "was_new_to_cache": was_new_to_cache,
            },
            source="faculty_page",
            occurred_at=datetime.now(UTC),
        )
    )
    return promoted


# ── public entrypoint ──────────────────────────────────────────────────────


def scrape_faculty_pages(
    universities: list[dict] | None = None,
) -> dict[str, int]:
    """Scrape top-school faculty pages, promote matching PhDs to incoming_ap.

    Args:
        universities: optional list to override the default UNIVERSITIES set
            (useful for testing). Each dict needs slug/name/url/selector.

    Returns:
        {"universities": N, "names_seen": A, "matched_researchers": M,
         "promoted_to_incoming_ap": P, "skipped_small": S, "errors": E}
    """
    counts = {
        "universities": 0,
        "names_seen": 0,
        "matched_researchers": 0,
        "promoted_to_incoming_ap": 0,
        "skipped_small": 0,
        "errors": 0,
    }

    pages = universities if universities is not None else UNIVERSITIES

    with (
        session_scope() as db,
        httpx.Client(headers=HEADERS, follow_redirects=True) as client,
    ):
        for entry in pages:
            counts["universities"] += 1
            slug = entry["slug"]
            inst_name = entry["name"]
            url = entry["url"]
            selector = entry["selector"]

            html = _fetch_html(client, url)
            if html is SMALL_PAGE:
                # 200 OK but tiny body — JS shell / stub, not a fetch failure.
                counts["skipped_small"] += 1
                time.sleep(1.0)
                continue
            if not html:
                counts["errors"] += 1
                # Sleep before moving on — be polite even on failure.
                time.sleep(1.0)
                continue

            extracted = _extract_names(html, selector, url)
            if not extracted:
                # Page loaded but selector returned nothing — structure changed.
                counts["errors"] += 1
                time.sleep(1.0)
                continue

            prev_names = _load_cache(slug)
            cur_names = [n for n, _ in extracted]
            counts["names_seen"] += len(cur_names)

            for name, prof_url in extracted:
                was_new = _normalize_for_match(name) not in {
                    _normalize_for_match(n) for n in prev_names
                }
                try:
                    matched_or_promoted = _match_and_promote(
                        db,
                        name,
                        institution_name=inst_name,
                        source_url=url,
                        profile_url=prof_url,
                        was_new_to_cache=was_new,
                    )
                except Exception:
                    counts["errors"] += 1
                    continue
                if matched_or_promoted:
                    counts["matched_researchers"] += 1
                    counts["promoted_to_incoming_ap"] += 1

            _save_cache(slug, cur_names, url)
            time.sleep(1.0)

    return counts
