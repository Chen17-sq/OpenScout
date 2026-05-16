"""Conference Program Committee scraper.

Being on the PC / AC / SAC of a top AI conference is a strong status signal,
particularly for early-career researchers — it means peers consider you senior
enough to make accept/reject calls. We surface those names as Signal rows so
the daily brief and `signal_tag` (deep_dive.py) can pick them up.

Scope:
  - NeurIPS / ICLR / ICML — the `.cc` pages with role headings + `reviewer-block`
    column divs (last few years).
  - CVPR — `cvpr.thecvf.com/Conferences/<year>/Organizers` (orgs only — no
    public AC list).
  - ACL — `2025.aclweb.org/organization` (orgs only — uses schema.org Person).
  - EMNLP — `<year>.emnlp.org/organization/` (orgs only).

What we record per matched researcher:
  Signal(type="conference_role", payload={conference, year, role}, source=...)
  e.g. {"conference": "NeurIPS", "year": 2025, "role": "Area Chair"}.

We DO NOT touch r.tags — `signal_tag` in deep_dive.py is the right place to
elevate "frequent SAC for NeurIPS" into a chip.

We SKIP plain "Reviewer" rows — too many, too noisy. SAC / AC / Top AC /
General Chair / Program Chair survive.
"""

from __future__ import annotations

import logging
import re
import time
from collections.abc import Iterable

import httpx
from selectolax.parser import HTMLParser
from sqlalchemy import select

from ..db import session_scope
from ..models import Researcher, Signal

logger = logging.getLogger(__name__)

UA = "OpenScout/0.6 (+https://github.com/Chen17-sq/OpenScout)"

# ── target pages ────────────────────────────────────────────────────────────
# (conference_key, year, url, parser_kind)
# parser_kind:
#   "cc_blocks"  — neurips.cc / iclr.cc / icml.cc Program-Committee pages.
#                  Sections delimited by <h2>Role</h2>, names inside
#                  <div class="reviewer-block">First Last<br>...</div>.
#   "cc_lists"   — neurips.cc/icml.cc Committees pages (organizers only).
#                  <h3>Role</h3><ul class="list-unstyled"><li>Name (Affiliation)</li>.
#   "acl_org"    — 20XX.aclweb.org/organization. <h2>Role</h2> followed by
#                  schema.org Person blocks with names in
#                  <h3 class="author__name" itemprop="name">.
TARGETS: list[tuple[str, int, str, str]] = [
    ("NeurIPS", 2025, "https://neurips.cc/Conferences/2025/ProgramCommittee", "cc_blocks"),
    ("NeurIPS", 2024, "https://neurips.cc/Conferences/2024/ProgramCommittee", "cc_blocks"),
    ("ICLR", 2025, "https://iclr.cc/Conferences/2025/ProgramCommittee", "cc_blocks"),
    ("ICLR", 2024, "https://iclr.cc/Conferences/2024/ProgramCommittee", "cc_blocks"),
    ("ICML", 2025, "https://icml.cc/Conferences/2025/ProgramCommittee", "cc_blocks"),
    ("ICML", 2025, "https://icml.cc/Conferences/2025/Committees", "cc_lists"),
    ("ICML", 2024, "https://icml.cc/Conferences/2024/Committees", "cc_lists"),
    ("CVPR", 2025, "https://cvpr.thecvf.com/Conferences/2025/Organizers", "cc_lists"),
    ("CVPR", 2024, "https://cvpr.thecvf.com/Conferences/2024/Organizers", "cc_lists"),
    ("ACL", 2025, "https://2025.aclweb.org/organization", "acl_org"),
    ("EMNLP", 2025, "https://2025.emnlp.org/organization/", "acl_org"),
    ("EMNLP", 2024, "https://2024.emnlp.org/organization/", "acl_org"),
]

# Roles we want to keep. Anything matching one of these substrings (case-
# insensitive) is recorded. Plain "Reviewer" / "Meta Reviewer" is excluded —
# we only want the senior tier on the cc pages (Senior Area Chair / Top Area
# Chair / All Area Chair — the last is still "Area Chair", the page just
# splits it from "Top"). Organizing-committee pages list chair titles
# directly, all of which are kept.
KEEP_ROLE_PATTERNS = [
    "senior area chair",
    "senior meta reviewer",  # ICML calls SAC this
    "top area chair",
    "area chair",
    "meta reviewer",  # ICML's term for AC
    "top meta reviewer",
    "outstanding meta reviewer",
    "general chair",
    "program chair",
    "program co-chair",
    "associate chair",
    "senior pc",
    "senior program committee",
    "track chair",
    "workshop chair",
    "tutorial chair",
    "publication chair",
    "publicity chair",
    "ethics chair",
    "demonstration chair",
    "tutorials chair",
    "doctoral consortium chair",
    "advisor to the program committee",
]
SKIP_ROLE_PATTERNS = [
    "main navigation",
    "all reviewer",
    "top reviewer",
    "outstanding reviewer",
    "reviewers",  # plain "Reviewers" section
    "scientific integrity",
    "local chair",
    "local organization",
    "social chair",
    "best paper committee",
    "visa chair",
    "documentation chair",
    "arr editors",
    "sponsorship chair",
    "diversity and inclusion",
    "social media",
    "website and conference app",
    "student volunteer",
    "internal communication",
    "industry track chair",  # business-side, low researcher signal
    "broadening participation",
    "ai art curator",
    "web developer",
    "conference producer",
    "technical chair",
    "finance chair",
    "handbook chair",
    "accessibility",
    "press chair",
    "publications chair",  # admin
    "workflow chair",
    "position paper track chair",  # rare
    "student research workshop",
    "ombuds",
    "for questions",  # ACL "Program Chairs" intro <ul> noise
]


def _normalize_role(raw: str) -> str | None:
    """Canonicalize a heading text to a short role label, or None if skipped.

    Returns a Title-Case role like "Area Chair" / "Senior Area Chair" /
    "General Chair" / "Program Chair". Returns None for plain reviewers,
    nav links, or non-PC entries.
    """
    if not raw:
        return None
    s = raw.strip().rstrip(":").strip()
    low = s.lower()
    if not low or len(low) > 80:
        return None
    # Order matters: skip-first wins on overlaps, but we want SAC to win over
    # bare "reviewer" if a page calls SACs "Senior Meta Reviewer".
    for kw in (
        "senior area chair",
        "senior meta reviewer",
        "top area chair",
        "top meta reviewer",
        "outstanding meta reviewer",
        "area chair",
        "meta reviewer",
        "associate chair",
    ):
        if kw in low:
            # Normalize the ICML term to "Area Chair" / "Senior Area Chair"
            if "senior" in low:
                return "Senior Area Chair"
            if "top" in low:
                return "Top Area Chair"
            if "outstanding" in low:
                return "Outstanding Area Chair"
            if "associate" in low:
                return "Associate Chair"
            return "Area Chair"

    for pat in SKIP_ROLE_PATTERNS:
        if pat in low:
            return None

    # Generic chair / committee roles — keep the heading as-is (Title Case),
    # but drop trailing year/conf cruft.
    for pat in KEEP_ROLE_PATTERNS:
        if pat in low:
            return s
    return None


# ── name cleaning ──────────────────────────────────────────────────────────
_NAME_TRAILING_PUNCT = re.compile(r"[\s,;.]+$")
_NAME_AFFIL_PAREN = re.compile(r"\s*\([^)]*\)\s*$")
_NON_NAME_CHARS = re.compile(r"[^\w\s\-.'À-ſĀ-ɏ]")


def _clean_name(raw: str) -> str | None:
    if not raw:
        return None
    s = raw.strip()
    # Drop "(Affiliation)" suffix that some pages embed inline
    s = _NAME_AFFIL_PAREN.sub("", s)
    s = _NAME_TRAILING_PUNCT.sub("", s).strip()
    # Reject obvious non-names
    if len(s) < 3 or len(s) > 80:
        return None
    if "@" in s or "http" in s.lower():
        return None
    if not re.search(r"[A-Za-zÀ-ſ]", s):
        return None
    # Names should have at least one space (first + last). Single tokens are
    # often section labels or "TBD".
    if " " not in s:
        return None
    return s


# ── parsers ─────────────────────────────────────────────────────────────────
# NOTE: selectolax's `.css()` returns matches grouped by selector, NOT in
# document order, so we cannot mix h2/h3 with sibling content in a single
# query. Use `.traverse()` for true depth-first document order, then filter.


def _node_classes(node) -> set[str]:
    cls = (node.attributes or {}).get("class") or ""
    return set(cls.split())


def _iter_cc_blocks(html: str) -> Iterable[tuple[str, str]]:
    """Yield (role, name) for neurips/iclr/icml ProgramCommittee pages.

    Layout: <h2>Role</h2> followed by one or more
    <div class="reviewer-block">Name<br>Name<br>...</div> blocks, until the
    next <h2>.
    """
    tree = HTMLParser(html)
    current_role: str | None = None
    for node in tree.root.traverse(include_text=False):
        tag = node.tag
        if tag in ("h2", "h3"):
            current_role = _normalize_role(node.text(strip=True))
            continue
        if not current_role:
            continue
        if tag == "div" and "reviewer-block" in _node_classes(node):
            # Names separated by <br>; selectolax returns text() with newlines
            # for <br>, so split on newline.
            block_text = node.text(separator="\n")
            for line in block_text.split("\n"):
                name = _clean_name(line)
                if name:
                    yield current_role, name


def _iter_cc_lists(html: str) -> Iterable[tuple[str, str]]:
    """Yield (role, name) for `*.cc` Committees and CVPR Organizers pages.

    Layout: <h3>Role</h3><ul class="list-unstyled"><li>Name (Affiliation)</li>.
    """
    tree = HTMLParser(html)
    current_role: str | None = None
    for node in tree.root.traverse(include_text=False):
        tag = node.tag
        if tag in ("h2", "h3"):
            current_role = _normalize_role(node.text(strip=True))
            continue
        if not current_role:
            continue
        if tag == "ul" and "list-unstyled" in _node_classes(node):
            for li in node.css("li"):
                raw = li.text(strip=True)
                name = _clean_name(raw)
                if name:
                    yield current_role, name


def _iter_acl_org(html: str) -> Iterable[tuple[str, str]]:
    """Yield (role, name) for ACL/EMNLP organization pages.

    Layout: <h2>Role</h2>, then schema.org Person divs with
    <h3 class="author__name" itemprop="name">Name</h3>. Walk the DOM in
    document order, tracking the most recent role heading.
    """
    tree = HTMLParser(html)
    current_role: str | None = None
    for node in tree.root.traverse(include_text=False):
        tag = node.tag
        if tag in ("h1", "h2"):
            current_role = _normalize_role(node.text(strip=True))
            continue
        if not current_role:
            continue
        if tag == "h3":
            attrs = node.attributes or {}
            classes = _node_classes(node)
            if "author__name" in classes or attrs.get("itemprop") == "name":
                name = _clean_name(node.text(strip=True))
                if name:
                    yield current_role, name


PARSERS = {
    "cc_blocks": _iter_cc_blocks,
    "cc_lists": _iter_cc_lists,
    "acl_org": _iter_acl_org,
}


# ── DB I/O ─────────────────────────────────────────────────────────────────
def _signal_source(conference: str, year: int) -> str:
    return f"{conference.lower()}-{year}-committee"


def _record_role(
    db,
    *,
    researcher: Researcher,
    conference: str,
    year: int,
    role: str,
) -> bool:
    """Insert a Signal if one for this (researcher, conf, year, role) doesn't
    already exist. Returns True if a new row was added.
    """
    source = _signal_source(conference, year)
    # Idempotency: we look up by (researcher, type, source) and then check
    # the role inside payload. This keeps us correct across reruns while
    # allowing a single researcher to hold multiple roles for one conference.
    existing = (
        db.execute(
            select(Signal).where(
                Signal.researcher_id == researcher.id,
                Signal.type == "conference_role",
                Signal.source == source,
            )
        )
        .scalars()
        .all()
    )
    for sig in existing:
        payload = sig.payload or {}
        if (
            payload.get("conference") == conference
            and payload.get("year") == year
            and payload.get("role") == role
        ):
            return False
    db.add(
        Signal(
            researcher_id=researcher.id,
            type="conference_role",
            payload={"conference": conference, "year": year, "role": role},
            source=source,
        )
    )
    return True


# ── main entry ─────────────────────────────────────────────────────────────
def scrape_conference_committees(
    *, sleep_between: float = 1.0, timeout: float = 25.0
) -> dict[str, int]:
    """Scrape PC/AC/SAC rolls from a handful of top AI conferences.

    Returns a counts dict — see module docstring. Defensive: each conference
    page is fetched and parsed in isolation, so one breaking page just bumps
    `errors` and the rest continue.
    """
    counts = {
        "conferences_scraped": 0,
        "names_seen": 0,
        "matched_researchers": 0,
        "roles_recorded": 0,
        "errors": 0,
    }

    client = httpx.Client(headers={"User-Agent": UA}, timeout=timeout, follow_redirects=True)
    try:
        for conf, year, url, kind in TARGETS:
            try:
                resp = client.get(url)
            except Exception as e:
                logger.warning("conference fetch failed %s: %s", url, e)
                counts["errors"] += 1
                continue
            if resp.status_code != 200:
                logger.info("conference page %s returned %s", url, resp.status_code)
                counts["errors"] += 1
                continue
            counts["conferences_scraped"] += 1

            parser = PARSERS.get(kind)
            if parser is None:
                logger.warning("no parser for kind=%s", kind)
                counts["errors"] += 1
                continue

            # Dedup names within a single page (some pages repeat names
            # across "Top AC" and "All AC" sections).
            seen_local: set[tuple[str, str]] = set()
            page_rows: list[tuple[str, str]] = []
            try:
                for role, name in parser(resp.text):
                    key = (role.lower(), name.lower())
                    if key in seen_local:
                        continue
                    seen_local.add(key)
                    page_rows.append((role, name))
            except Exception as e:
                logger.warning("parser failed for %s: %s", url, e)
                counts["errors"] += 1
                continue

            counts["names_seen"] += len(page_rows)
            if not page_rows:
                logger.info("no names extracted from %s", url)

            with session_scope() as db:
                for role, name in page_rows:
                    matches = (
                        db.execute(select(Researcher).where(Researcher.name_en == name))
                        .scalars()
                        .all()
                    )
                    if not matches:
                        continue
                    # Multiple homonyms — skip to avoid mis-attributing a senior
                    # researcher's signal to an early-career namesake (the
                    # signal is meant to be a status marker, after all).
                    if len(matches) > 1:
                        logger.debug(
                            "ambiguous name %r matched %d researchers; skipping",
                            name,
                            len(matches),
                        )
                        continue
                    researcher = matches[0]
                    counts["matched_researchers"] += 1
                    if _record_role(
                        db,
                        researcher=researcher,
                        conference=conf,
                        year=year,
                        role=role,
                    ):
                        counts["roles_recorded"] += 1

            time.sleep(sleep_between)
    finally:
        client.close()

    return counts
