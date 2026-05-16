"""Affiliation discovery — populate `Researcher.current_affiliation_id`.

Most auto-discovered researchers (via surname inference, peer inheritance,
co-author byline) land with `current_affiliation_id = null` because their
seed signal didn't carry an institution. The downstream UI then shows
"机构: —" which is uninvestable.

Strategy per researcher — try each in order, stop at first hit:

  1. OpenAlex     `last_known_institution{,s}` from authors/{id} endpoint
  2. Semantic Scholar  `affiliations[0]` from author/{id}?fields=affiliations
  3. Bio leftover  parse "<Institution> · (per Semantic Scholar)" set by
                   the older S2 enrichment path before this module existed

For each hit, we fuzzy-match the institution name against rows already in
the `institutions` table. When nothing matches BUT we have a clear name,
we auto-create the Institution row (country may be filled in from the
OpenAlex `country_code` when available).

Scope: only touches researchers where `current_affiliation_id IS NULL`
AND one of {openalex_id, semantic_scholar_id, bio matches the S2-leftover
shape} is set. Cheap to re-run — idempotent on already-resolved rows.
"""

from __future__ import annotations

import re
import time

import httpx
from sqlalchemy import or_, select

from ..db import session_scope
from ..models import Institution, Researcher

HEADERS = {"User-Agent": "OpenScout/1.7 (+https://github.com/Chen17-sq/OpenScout)"}

# Bio shape left by scraper.semanticscholar / deep_dive._semantic_scholar_discover:
#   "<institution name> · (per Semantic Scholar)"
_BIO_S2_PATTERN = re.compile(r"^(.+?)\s*·\s*\(per Semantic Scholar\)", re.IGNORECASE)

# Normalization: strip "The ", "University of ", trailing punctuation, lowercase,
# collapse whitespace. Used for fuzzy matching ONLY — preserves the original
# string for display.
_PREFIX_RE = re.compile(r"^(the\s+|university\s+of\s+)", re.IGNORECASE)


def _normalize(name: str) -> str:
    s = (name or "").strip().lower()
    # repeat once: "The University of X" → "X"
    for _ in range(2):
        s = _PREFIX_RE.sub("", s).strip()
    s = re.sub(r"[\s\-_,.;:()/]+", " ", s).strip()
    return s


def _match_institution(db, raw_name: str) -> Institution | None:
    """Find an Institution row whose name fuzzy-matches `raw_name`.

    Case-insensitive, "The"/"University of" prefix-stripped. Returns the
    first match by id ASC (deterministic) or None.
    """
    if not raw_name:
        return None
    target = _normalize(raw_name)
    if not target:
        return None
    # Pull a candidate set with a cheap LIKE, then exact-compare after normalize.
    # Avoid loading the full institutions table when DB grows.
    first_word = target.split(" ", 1)[0]
    if len(first_word) < 3:
        # Too short to be useful — fall back to full scan
        candidates = list(db.execute(select(Institution)).scalars().all())
    else:
        like = f"%{first_word}%"
        candidates = list(
            db.execute(
                select(Institution).where(
                    or_(Institution.name.ilike(like), Institution.name_zh.ilike(like))
                )
            )
            .scalars()
            .all()
        )
    for inst in candidates:
        if _normalize(inst.name or "") == target:
            return inst
        if inst.name_zh and _normalize(inst.name_zh) == target:
            return inst
    return None


def _get_or_create(
    db,
    raw_name: str,
    *,
    openalex_id: str | None = None,
    country: str | None = None,
) -> tuple[Institution | None, bool]:
    """Match existing row OR create a new Institution. Returns (inst, created)."""
    if not raw_name or not raw_name.strip():
        return None, False
    existing = _match_institution(db, raw_name)
    if existing:
        # Opportunistically fill in openalex_id / country if missing
        if openalex_id and not existing.openalex_id:
            existing.openalex_id = openalex_id
        if country and not existing.country:
            existing.country = country.upper()[:8]
        return existing, False
    name = raw_name.strip()[:255]
    if not name:
        return None, False
    # Name must be unique on `institutions.name`; if another row exists with
    # exactly this name (e.g. case-different but we missed it in normalize),
    # bail to that one rather than tripping the unique constraint.
    pre = db.execute(select(Institution).where(Institution.name == name)).scalar_one_or_none()
    if pre is not None:
        return pre, False
    inst = Institution(
        name=name,
        country=country.upper()[:8] if country else None,
        openalex_id=openalex_id,
    )
    db.add(inst)
    db.flush()  # need .id immediately for the FK on Researcher
    return inst, True


# ── source 1: OpenAlex ──────────────────────────────────────────────────────


def _openalex_lookup(
    http: httpx.Client, openalex_id: str
) -> tuple[str | None, str | None, str | None]:
    """Return (institution_name, openalex_inst_id, country_code) or all None."""
    aid = openalex_id.rsplit("/", 1)[-1]
    try:
        r = http.get(f"https://api.openalex.org/authors/{aid}", timeout=15.0)
        if r.status_code != 200:
            return None, None, None
        data = r.json()
    except Exception:
        return None, None, None
    inst = data.get("last_known_institution") or {}
    if not inst:
        # OpenAlex switched to last_known_institutions (plural) in 2024
        insts = data.get("last_known_institutions") or []
        inst = insts[0] if insts else {}
    if not inst:
        return None, None, None
    name = inst.get("display_name")
    oa_id = inst.get("id")
    cc = inst.get("country_code")
    return name, oa_id, cc


# ── source 2: Semantic Scholar ──────────────────────────────────────────────


def _semantic_scholar_lookup(http: httpx.Client, s2_id: str) -> str | None:
    """Return the first affiliation string or None."""
    try:
        from ..config import settings
    except Exception:
        settings = None  # type: ignore[assignment]

    headers: dict[str, str] = {}
    if settings is not None and getattr(settings, "semantic_scholar_api_key", None):
        headers["x-api-key"] = settings.semantic_scholar_api_key

    try:
        r = http.get(
            f"https://api.semanticscholar.org/graph/v1/author/{s2_id}",
            params={"fields": "affiliations"},
            headers=headers,
            timeout=15.0,
        )
        if r.status_code != 200:
            return None
        affs = r.json().get("affiliations") or []
    except Exception:
        return None
    for a in affs:
        if isinstance(a, str) and a.strip():
            return a.strip()
    return None


# ── source 3: bio leftover ──────────────────────────────────────────────────


def _bio_lookup(bio: str | None) -> str | None:
    if not bio:
        return None
    m = _BIO_S2_PATTERN.match(bio.strip())
    if not m:
        return None
    name = m.group(1).strip()
    return name or None


# ── orchestrator ────────────────────────────────────────────────────────────


def discover_affiliations(limit: int | None = None) -> dict[str, int]:
    """Populate `current_affiliation_id` for researchers that lack one.

    Returns: {"scanned": N, "matched_openalex": A, "matched_s2": B,
              "matched_bio": C, "created_institution": D, "errors": E}
    """
    counts = {
        "scanned": 0,
        "matched_openalex": 0,
        "matched_s2": 0,
        "matched_bio": 0,
        "created_institution": 0,
        "errors": 0,
    }

    bio_like = "% · (per Semantic Scholar)"

    with session_scope() as db, httpx.Client(headers=HEADERS, follow_redirects=True) as http:
        stmt = select(Researcher).where(
            Researcher.current_affiliation_id.is_(None),
            or_(
                Researcher.openalex_id.is_not(None),
                Researcher.semantic_scholar_id.is_not(None),
                Researcher.bio.ilike(bio_like),
            ),
        )
        if limit:
            stmt = stmt.limit(limit)
        rows = list(db.execute(stmt).scalars().all())

        for r in rows:
            counts["scanned"] += 1

            inst_name: str | None = None
            inst_oa_id: str | None = None
            inst_country: str | None = None
            source: str | None = None

            # 1) OpenAlex
            if r.openalex_id:
                try:
                    name, oa_id, cc = _openalex_lookup(http, r.openalex_id)
                except Exception:
                    counts["errors"] += 1
                    name, oa_id, cc = None, None, None
                if name:
                    inst_name, inst_oa_id, inst_country = name, oa_id, cc
                    source = "openalex"
                time.sleep(0.15)

            # 2) Semantic Scholar
            if not inst_name and r.semantic_scholar_id:
                try:
                    name = _semantic_scholar_lookup(http, r.semantic_scholar_id)
                except Exception:
                    counts["errors"] += 1
                    name = None
                if name:
                    inst_name = name
                    source = "semantic_scholar"
                time.sleep(0.20)

            # 3) bio leftover
            if not inst_name:
                name = _bio_lookup(r.bio)
                if name:
                    inst_name = name
                    source = "bio_s2_leftover"

            if not inst_name:
                continue

            try:
                inst, created = _get_or_create(
                    db,
                    inst_name,
                    openalex_id=inst_oa_id,
                    country=inst_country,
                )
            except Exception:
                counts["errors"] += 1
                continue

            if not inst:
                continue
            if created:
                counts["created_institution"] += 1

            r.current_affiliation_id = inst.id
            r.affiliation_source = source

            if source == "openalex":
                counts["matched_openalex"] += 1
            elif source == "semantic_scholar":
                counts["matched_s2"] += 1
            elif source == "bio_s2_leftover":
                counts["matched_bio"] += 1

    return counts
