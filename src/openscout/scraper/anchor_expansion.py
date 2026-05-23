"""Expand the anchor roster via OpenAlex top-cited authors per concept + HuggingFace Daily Papers.

Why: we started with 67 hand-curated anchors (high/medium confidence). Coverage of
the user's thesis areas (embodied AI, world models, AI4Science) is too sparse to
rank against. This module auto-discovers `medium`-confidence anchors from two
high-signal sources so the investment-ranking page has enough breadth.

Sources:
  1. OpenAlex `/works` filtered by concept + 2024-2025, sorted by citations.
     We take the FIRST and LAST author of each work (the people who actually
     drove it, not all 12 co-authors). These get `affiliation_source='openalex'`
     and inherit the matched author's institution when our DB already knows it.
  2. HuggingFace Daily Papers — the curated trending list. First-author only.

Outputs `confidence_level='medium'` for everything inserted, so existing
hand-curated `high` anchors keep their primacy in `/investment` ranking but
auto-discovered rows still surface above the `low` noise floor.

Skip rules:
  - Skip if openalex_id already matches an existing Researcher.
  - Skip if name_en exact-matches an existing Researcher (consistent with
    arxiv._upsert_researcher_by_name behavior; intentional name-collision
    behavior — the dedupe pass refines later).

Rate limit: OpenAlex polite pool is 10 req/sec with mailto. We sleep 0.2s
between requests which is well under the cap and gives a comfortable margin
when paginating across 7 concepts × 25 results.
"""

import re
import time

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..db import session_scope
from ..models import Institution, Researcher

OPENALEX_API = "https://api.openalex.org/works"
HF_DAILY_API = "https://huggingface.co/api/daily_papers"
POLITE_MAILTO = "openscout-public@github.com"
USER_AGENT = "OpenScout/0.5 (+https://github.com/Chen17-sq/OpenScout)"

# OpenAlex concept IDs covering the user's investment thesis.
# These are the *verified* IDs as of 2025-05 — the IDs floating around in older
# docs (C2776035688 for "Robotics", etc.) are stale concept-tag artifacts that
# resolve to unrelated topics like "Affect (linguistics)" today. Verified via:
#   GET https://api.openalex.org/concepts?search=<name>
CONCEPTS: dict[str, str] = {
    "C34413123": "Robotics",
    "C31972630": "Computer vision",
    "C100609095": "Embodied cognition",
    "C108583219": "Deep learning",
    "C97541855": "Reinforcement learning",
    "C70721500": "Computational biology",
    "C147597530": "Computational chemistry",
}


def _slug_from_name(name: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")
    return s or "unknown"


def _generate_unique_slug(db: Session, name: str) -> str:
    """kebab-case the name, append `-2/-3/...` on collision. Mirrors arxiv._generate_unique_slug."""
    base = _slug_from_name(name)
    candidate = base
    n = 1
    while db.execute(select(Researcher.id).where(Researcher.slug == candidate)).first():
        n += 1
        candidate = f"{base}-{n}"
    return candidate


def _institution_id_for_openalex(db: Session, openalex_inst_id: str | None) -> int | None:
    """Look up our local Institution.id by OpenAlex ID. Returns None if not seeded."""
    if not openalex_inst_id:
        return None
    row = db.execute(
        select(Institution.id).where(Institution.openalex_id == openalex_inst_id)
    ).scalar_one_or_none()
    return int(row) if row else None


def _researcher_exists(db: Session, *, openalex_id: str | None, name_en: str) -> Researcher | None:
    """Return existing Researcher row matching either field, else None.

    OpenAlex ID is the high-confidence key; name is the fallback (consistent
    with arxiv._upsert_researcher_by_name). If both miss → new row.
    """
    if openalex_id:
        existing = db.execute(
            select(Researcher).where(Researcher.openalex_id == openalex_id)
        ).scalar_one_or_none()
        if existing:
            return existing
    existing = db.execute(
        select(Researcher).where(Researcher.name_en == name_en)
    ).scalar_one_or_none()
    return existing


def _upsert_anchor_from_openalex(
    db: Session,
    *,
    name_en: str,
    openalex_author_id: str | None,
    institutions: list[dict],
    concept_label: str,
) -> tuple[Researcher, bool]:
    """Create a `medium`-confidence Researcher if absent. Returns (researcher, created).

    `institutions` is the OpenAlex `authorships[i].institutions` list — we pick
    the first one whose country_code we can use and try to match it to our
    `Institution` rows by OpenAlex ID.
    """
    existing = _researcher_exists(db, openalex_id=openalex_author_id, name_en=name_en)
    if existing:
        return existing, False

    # Pick the primary institution + country from the first one with an ID.
    primary_inst = institutions[0] if institutions else {}
    inst_openalex_id = primary_inst.get("id") if isinstance(primary_inst, dict) else None
    country = (primary_inst.get("country_code") or "").upper() or None

    affiliation_id = _institution_id_for_openalex(db, inst_openalex_id)

    slug = _generate_unique_slug(db, name_en)
    researcher = Researcher(
        slug=slug,
        name_en=name_en,
        openalex_id=openalex_author_id,
        country=country,
        country_source="openalex" if country else None,
        current_affiliation_id=affiliation_id,
        affiliation_source="openalex" if affiliation_id else None,
        confidence_level="medium",
    )
    db.add(researcher)
    db.flush()
    print(f"  + {name_en:32s} via OpenAlex [{concept_label}]")
    return researcher, True


def _fetch_top_works(client: httpx.Client, concept_id: str, *, limit: int) -> list[dict]:
    """Hit OpenAlex /works with concept + recent-year + cited_by_count sort."""
    params = {
        "filter": f"concepts.id:{concept_id},publication_year:2024-2025,type:article",
        "sort": "cited_by_count:desc",
        "per-page": min(limit, 50),
        # Pull only the fields we need — keeps payload small.
        "select": "id,title,cited_by_count,authorships",
        "mailto": POLITE_MAILTO,
    }
    r = client.get(OPENALEX_API, params=params, timeout=30.0)
    r.raise_for_status()
    return (r.json() or {}).get("results") or []


def _extract_anchor_candidates(work: dict) -> list[tuple[str, str | None, list[dict]]]:
    """Return [(name_en, openalex_author_id, institutions), ...] for first + last authors.

    Skips entries without at least one institution set (filters out
    unaffiliated/disambiguation-failed authors which are noisy).
    """
    authorships = work.get("authorships") or []
    if not authorships:
        return []
    picks = [authorships[0]]
    if len(authorships) > 1:
        picks.append(authorships[-1])

    out: list[tuple[str, str | None, list[dict]]] = []
    for a in picks:
        author = a.get("author") or {}
        name = (author.get("display_name") or "").strip()
        if not name:
            continue
        # `institutions` is per-affiliation; `last_known_institutions` lives on
        # the author object itself. Prefer per-paper institutions (more accurate
        # at the time of that work), fall back to author-level.
        insts = a.get("institutions") or author.get("last_known_institutions") or []
        if not insts:
            continue  # require at least one — filters out junk authorships
        out.append((name, author.get("id"), insts))
    return out


def _expand_via_openalex(limit_per_concept: int = 25) -> dict[str, int]:
    """Walk each concept, pull top works, upsert first+last authors."""
    counts = {"works_fetched": 0, "candidates": 0, "added": 0, "errors": 0}

    headers = {"User-Agent": USER_AGENT}
    with httpx.Client(headers=headers, timeout=30.0) as client:
        for concept_id, concept_label in CONCEPTS.items():
            try:
                works = _fetch_top_works(client, concept_id, limit=limit_per_concept)
            except Exception as e:
                print(f"  ! {concept_label} ({concept_id}): {type(e).__name__}: {e}")
                counts["errors"] += 1
                time.sleep(0.5)
                continue
            counts["works_fetched"] += len(works)

            # Upsert in one session per concept so a failure mid-concept doesn't
            # blow away the whole batch.
            with session_scope() as db:
                for work in works:
                    for name, oa_author_id, insts in _extract_anchor_candidates(work):
                        counts["candidates"] += 1
                        try:
                            _, created = _upsert_anchor_from_openalex(
                                db,
                                name_en=name,
                                openalex_author_id=oa_author_id,
                                institutions=insts,
                                concept_label=concept_label,
                            )
                            if created:
                                counts["added"] += 1
                        except Exception as e:  # noqa: BLE001
                            print(f"  ! upsert {name}: {type(e).__name__}: {e}")
                            counts["errors"] += 1
            # Respect the 10 req/sec polite limit with generous margin.
            time.sleep(0.2)
    return counts


def _expand_via_hf_daily(limit: int = 100) -> dict[str, int]:
    """Pull first-authors from HF Daily Papers. Lighter source — no institutions."""
    counts = {"fetched": 0, "added": 0, "errors": 0}

    headers = {"User-Agent": USER_AGENT}
    try:
        with httpx.Client(headers=headers, timeout=30.0) as client:
            r = client.get(HF_DAILY_API, params={"limit": limit})
            r.raise_for_status()
            data = r.json() or []
    except Exception as e:
        print(f"  ! HF Daily: {type(e).__name__}: {e}")
        counts["errors"] += 1
        return counts

    if not isinstance(data, list):
        return counts
    counts["fetched"] = len(data)

    with session_scope() as db:
        for entry in data:
            paper_meta = entry.get("paper") or entry
            authors = paper_meta.get("authors") or []
            if not authors:
                continue
            first = authors[0]
            name = (first.get("name") if isinstance(first, dict) else str(first) or "").strip()
            if not name:
                continue
            # HF doesn't surface OpenAlex IDs; we rely on name match alone.
            existing = _researcher_exists(db, openalex_id=None, name_en=name)
            if existing:
                continue
            slug = _generate_unique_slug(db, name)
            db.add(
                Researcher(
                    slug=slug,
                    name_en=name,
                    confidence_level="medium",
                    affiliation_source="huggingface_daily",
                )
            )
            try:
                db.flush()
            except Exception as e:  # noqa: BLE001
                print(f"  ! HF insert {name}: {type(e).__name__}: {e}")
                counts["errors"] += 1
                continue
            counts["added"] += 1
            print(f"  + {name:32s} via HuggingFace Daily")
    return counts


def expand_anchors(limit_per_concept: int = 25) -> dict[str, int]:
    """Public entry point. Returns combined counts from both sources.

    Idempotent — re-running only adds rows that don't yet exist by openalex_id
    or exact name match. Safe to schedule weekly.
    """
    print("== OpenAlex top-cited-per-concept ==")
    openalex_counts = _expand_via_openalex(limit_per_concept=limit_per_concept)

    print("== HuggingFace Daily Papers ==")
    hf_counts = _expand_via_hf_daily(limit=100)

    return {
        "openalex_works_fetched": openalex_counts["works_fetched"],
        "openalex_candidates": openalex_counts["candidates"],
        "openalex_added": openalex_counts["added"],
        "openalex_errors": openalex_counts["errors"],
        "hf_fetched": hf_counts["fetched"],
        "hf_added": hf_counts["added"],
        "hf_errors": hf_counts["errors"],
        "total_added": openalex_counts["added"] + hf_counts["added"],
    }
