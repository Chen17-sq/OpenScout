"""OpenAlex enricher — authoritative source for Chinese names, citations, tags.

Strategy: name-only search returns the wrong person for common Chinese names
(e.g. there are dozens of "Jun Zhu" in OpenAlex). So:
  1. For each seed institution (Tsinghua, DeepMind, Sakana AI, …), resolve to an
     OpenAlex Institution ID and cache on `Institution.openalex_id`.
  2. When enriching a researcher with a `current_affiliation_id`, FILTER the
     Authors search by `last_known_institutions.id = <inst_openalex_id>`.
  3. Only fall back to name-only search for researchers without affiliation
     (rare for our anchors, common for auto-discovered low-confidence rows).

Provenance for Chinese name (`name_zh_source`):
  - "manual"           — set by hand in seeds/researchers.yaml
  - "openalex_alt"     — found in display_name_alternatives (CJK detected)
  - NEVER guessed      — left null when no source has it
"""

import re
import time
from typing import Any, Optional

import pyalex
from pyalex import Authors, Institutions
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..db import session_scope
from ..models import Institution as InstitutionModel
from ..models import Researcher

pyalex.config.email = "openscout-public@github.com"

_CJK_RE = re.compile(r"[一-鿿]")


def _has_cjk(s: str | None) -> bool:
    return bool(s and _CJK_RE.search(s))


def _pick_chinese_name(alternatives: list[str] | None) -> Optional[str]:
    if not alternatives:
        return None
    for alt in alternatives:
        if _has_cjk(alt):
            return alt.strip()
    return None


def _normalize_name(s: str) -> str:
    return " ".join(s.strip().lower().split())


def resolve_institutions(limit: Optional[int] = None) -> dict[str, int]:
    """Resolve each seed institution → OpenAlex ID. Idempotent."""
    counts = {"attempted": 0, "matched": 0, "skipped_already_set": 0, "no_match": 0}
    with session_scope() as db:
        stmt = select(InstitutionModel).where(InstitutionModel.openalex_id.is_(None))
        if limit:
            stmt = stmt.limit(limit)
        rows = list(db.execute(stmt).scalars().all())
        for inst in rows:
            counts["attempted"] += 1
            try:
                results = Institutions().search(inst.name).get(per_page=3)
            except Exception:
                continue
            if not results:
                counts["no_match"] += 1
                continue
            # Prefer the result whose country matches our seed entry (if both set).
            picked = results[0]
            if inst.country:
                in_country = [
                    r for r in results if (r.get("country_code") or "").upper() == inst.country.upper()
                ]
                if in_country:
                    picked = in_country[0]
            inst.openalex_id = picked["id"]
            counts["matched"] += 1
            time.sleep(0.15)
    return counts


def _find_openalex_author(
    name_en: str,
    *,
    affiliation_openalex_id: Optional[str] = None,
    country_hint: Optional[str] = None,
) -> Optional[dict]:
    """Best-effort lookup. Prefers exact name + institution filter."""
    target = _normalize_name(name_en)

    if affiliation_openalex_id:
        try:
            results = (
                Authors()
                .search(name_en)
                .filter(last_known_institutions={"id": affiliation_openalex_id})
                .get(per_page=10)
            )
        except Exception:
            results = []
        # Exact name match among institution-filtered → strong signal.
        exact = [r for r in results if _normalize_name(r.get("display_name") or "") == target]
        if exact:
            return max(exact, key=lambda r: r.get("works_count") or 0)
        if results:
            # Even non-exact (e.g. "J. Zhu" for "Jun Zhu"), trust the institution match.
            return max(results, key=lambda r: r.get("works_count") or 0)

    # Fall back to name + country
    try:
        q = Authors().search(name_en)
        if country_hint:
            q = q.filter(last_known_institutions={"country_code": country_hint.lower()})
        results = q.get(per_page=10)
    except Exception:
        return None
    if not results:
        return None
    exact = [r for r in results if _normalize_name(r.get("display_name") or "") == target]
    if exact:
        return max(exact, key=lambda r: r.get("works_count") or 0)
    return None


def _extract_tags(author: dict) -> list[dict]:
    """OpenAlex x_concepts → tag schema. Scores are 0-1 floats."""
    concepts = author.get("x_concepts") or author.get("concepts") or []
    out: list[dict] = []
    for c in concepts[:10]:
        label = c.get("display_name")
        score = c.get("score")
        level = c.get("level", 0)
        if not label or score is None:
            continue
        s = float(score)
        # Keep mid-confidence and above; skip level-0 mega-concepts ("Computer science")
        # when they're not the strongest signal.
        if s < 0.30:
            continue
        out.append(
            {
                "label": label,
                "score": round(s, 3),
                "level": int(level),
                "wikidata": c.get("wikidata"),
            }
        )
    return out


def enrich_researcher(db: Session, researcher: Researcher) -> dict[str, Any]:
    """Mutate `researcher` with OpenAlex data. Returns diagnostics dict."""
    if researcher.openalex_id:
        return {"already_enriched": True}

    aff_openalex_id: Optional[str] = None
    if researcher.current_affiliation_id:
        inst = db.execute(
            select(InstitutionModel).where(InstitutionModel.id == researcher.current_affiliation_id)
        ).scalar_one_or_none()
        if inst and inst.openalex_id:
            aff_openalex_id = inst.openalex_id

    author = _find_openalex_author(
        researcher.name_en,
        affiliation_openalex_id=aff_openalex_id,
        country_hint=researcher.country,
    )
    if not author:
        return {"matched": False}

    updated: dict[str, Any] = {"matched": True, "openalex_id": author.get("id")}
    researcher.openalex_id = author.get("id")

    if author.get("works_count") is not None:
        researcher.works_count = int(author["works_count"])
        updated["works_count"] = researcher.works_count
    if author.get("cited_by_count") is not None:
        researcher.citation_count = int(author["cited_by_count"])
        updated["citation_count"] = researcher.citation_count

    stats = author.get("summary_stats") or {}
    if stats.get("h_index") is not None:
        researcher.h_index = int(stats["h_index"])
        updated["h_index"] = researcher.h_index

    if author.get("orcid") and not researcher.orcid:
        researcher.orcid = author["orcid"]
        updated["orcid"] = researcher.orcid

    if not researcher.name_zh:
        zh = _pick_chinese_name(author.get("display_name_alternatives"))
        if zh:
            researcher.name_zh = zh
            researcher.name_zh_source = "openalex_alt"
            updated["name_zh"] = zh

    if not researcher.country:
        inst_data = author.get("last_known_institution") or {}
        if not inst_data:
            # OpenAlex moved to last_known_institutions (plural) in 2024
            insts = author.get("last_known_institutions") or []
            inst_data = insts[0] if insts else {}
        cc = (inst_data.get("country_code") or "").upper()
        if cc:
            researcher.country = cc
            updated["country"] = cc

    tags = _extract_tags(author)
    if tags:
        researcher.tags = tags
        updated["tags"] = len(tags)

    if researcher.confidence_level == "low":
        researcher.confidence_level = "medium"
        updated["confidence_bumped"] = True

    return updated


def enrich_all(
    limit: int = 200,
    only_confidence: list[str] | None = None,
    sleep_between: float = 0.15,
) -> dict[str, int]:
    counts = {
        "attempted": 0,
        "matched": 0,
        "with_zh_name": 0,
        "with_tags": 0,
        "errors": 0,
    }
    with session_scope() as db:
        stmt = select(Researcher).where(Researcher.openalex_id.is_(None))
        if only_confidence:
            stmt = stmt.where(Researcher.confidence_level.in_(only_confidence))
        stmt = stmt.limit(limit)
        rows = list(db.execute(stmt).scalars().all())

        for r in rows:
            counts["attempted"] += 1
            try:
                res = enrich_researcher(db, r)
            except Exception:
                counts["errors"] += 1
                continue
            if res.get("matched"):
                counts["matched"] += 1
            if res.get("name_zh"):
                counts["with_zh_name"] += 1
            if res.get("tags"):
                counts["with_tags"] += 1
            time.sleep(sleep_between)
    return counts


def reset_low_quality_matches() -> int:
    """Clear openalex_id for rows that were matched without institution filter.

    Heuristic: clear when researcher has `current_affiliation_id` set (we should
    have used it) but `openalex_id` was set anyway — those used the old
    name-only search and may be wrong.
    """
    from sqlalchemy import update

    with session_scope() as db:
        result = db.execute(
            update(Researcher)
            .where(
                Researcher.current_affiliation_id.is_not(None),
                Researcher.openalex_id.is_not(None),
            )
            .values(openalex_id=None, h_index=None, works_count=None, citation_count=None, tags=None)
        )
        return int(result.rowcount or 0)


def assign_signature_papers() -> int:
    """For each researcher with papers, pick a signature paper.

    Algorithm: highest paper.citation_count among first-authored papers; falls
    back to overall highest if no first-author papers exist.
    """
    from sqlalchemy import desc

    from ..models import Paper, PaperAuthor

    updated = 0
    with session_scope() as db:
        researcher_ids = [
            rid for (rid,) in db.execute(select(PaperAuthor.researcher_id).distinct()).all()
        ]
        for rid in researcher_ids:
            first_paper = db.execute(
                select(Paper)
                .join(PaperAuthor, PaperAuthor.paper_id == Paper.id)
                .where(PaperAuthor.researcher_id == rid, PaperAuthor.position == 1)
                .order_by(desc(Paper.citation_count), desc(Paper.first_seen_at))
                .limit(1)
            ).scalar_one_or_none()
            if not first_paper:
                first_paper = db.execute(
                    select(Paper)
                    .join(PaperAuthor, PaperAuthor.paper_id == Paper.id)
                    .where(PaperAuthor.researcher_id == rid)
                    .order_by(desc(Paper.citation_count), desc(Paper.first_seen_at))
                    .limit(1)
                ).scalar_one_or_none()
            if first_paper:
                r = db.execute(select(Researcher).where(Researcher.id == rid)).scalar_one_or_none()
                if r and r.signature_paper_id != first_paper.id:
                    r.signature_paper_id = first_paper.id
                    updated += 1
    return updated
