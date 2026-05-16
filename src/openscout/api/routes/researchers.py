from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import desc, func, or_, select
from sqlalchemy.orm import Session

from ...db import get_db
from ...models import Institution, Paper, PaperAuthor, PaperTopic, Relationship, Researcher, Topic
from ...scraper.deep_dive import deep_dive_one

router = APIRouter()


@router.post("/{slug}/deep-dive")
def trigger_deep_dive(slug: str, force: bool = Query(False)) -> dict:
    """Run all 5 deep-dive sources for this researcher (~30s). Skips sources
    that ran successfully in the last 30 days unless `force=true`.
    """
    result = deep_dive_one(slug, force=force)
    if result.get("error"):
        raise HTTPException(404, detail=result["error"])
    return result


@router.get("/")
def list_researchers(
    db: Session = Depends(get_db),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    stage: str | None = Query(None, description="phd / postdoc / incoming_ap / ap / senior"),
    confidence: str | None = Query(None, description="low / medium / high"),
    topic: str | None = Query(None, description="topic slug"),
    country: str | None = Query(None, description="ISO country code"),
    q: str | None = Query(None, description="search by name (case-insensitive substring)"),
    sort: str = Query("papers", description="papers / citations / h_index / name"),
) -> dict:
    n_papers = func.count(PaperAuthor.paper_id).label("n")
    base = (
        select(Researcher, n_papers)
        .outerjoin(PaperAuthor, PaperAuthor.researcher_id == Researcher.id)
        .group_by(Researcher.id)
    )

    if stage:
        base = base.where(Researcher.current_role == stage)
    if confidence:
        base = base.where(Researcher.confidence_level == confidence)
    if country:
        base = base.where(Researcher.country == country.upper())
    if q:
        base = base.where(
            or_(Researcher.name_en.ilike(f"%{q}%"), Researcher.name_zh.ilike(f"%{q}%"))
        )
    if topic:
        topic_row = db.execute(select(Topic).where(Topic.slug == topic)).scalar_one_or_none()
        if topic_row:
            base = base.join(PaperTopic, PaperTopic.paper_id == PaperAuthor.paper_id).where(
                PaperTopic.topic_id == topic_row.id
            )

    total = int(db.execute(select(func.count()).select_from(base.subquery())).scalar() or 0)

    sort_map = {
        "papers": (desc(n_papers), Researcher.name_en),
        "citations": (desc(Researcher.citation_count).nulls_last(), desc(n_papers)),
        "h_index": (desc(Researcher.h_index).nulls_last(), desc(n_papers)),
        "name": (Researcher.name_en, desc(n_papers)),
    }
    order_cols = sort_map.get(sort, sort_map["papers"])

    stmt = base.order_by(*order_cols).limit(limit).offset(offset)
    rows = db.execute(stmt).all()
    return {
        "total": total,
        "limit": limit,
        "offset": offset,
        "items": [{**_serialize_summary(r), "n_papers": int(n)} for r, n in rows],
    }


@router.get("/{slug}")
def get_researcher(slug: str, db: Session = Depends(get_db)) -> dict:
    r = db.execute(select(Researcher).where(Researcher.slug == slug)).scalar_one_or_none()
    if not r:
        raise HTTPException(404, detail=f"researcher {slug!r} not found")

    affiliation = None
    if r.current_affiliation_id:
        inst = db.execute(
            select(Institution).where(Institution.id == r.current_affiliation_id)
        ).scalar_one_or_none()
        if inst:
            affiliation = {
                "name": inst.name,
                "name_zh": inst.name_zh,
                "country": inst.country,
                "type": inst.type,
            }

    advisor = None
    if r.advisor_id:
        adv = db.execute(
            select(Researcher).where(Researcher.id == r.advisor_id)
        ).scalar_one_or_none()
        if adv:
            advisor = {"slug": adv.slug, "name_en": adv.name_en, "name_zh": adv.name_zh}

    # Inferred lineage edges TO this researcher (the advisor relationships pointing at them)
    inferred_advisors = []
    rel_rows = db.execute(
        select(Relationship, Researcher)
        .join(Researcher, Researcher.id == Relationship.from_researcher_id)
        .where(Relationship.to_researcher_id == r.id, Relationship.type == "advisor")
    ).all()
    for rel, adv in rel_rows:
        inferred_advisors.append(
            {
                "slug": adv.slug,
                "name_en": adv.name_en,
                "name_zh": adv.name_zh,
                "confidence": rel.confidence,
                "evidence": rel.evidence,
            }
        )

    # Students whose advisor is set to this researcher
    students_rows = (
        db.execute(select(Researcher).where(Researcher.advisor_id == r.id)).scalars().all()
    )
    students = [
        {
            "slug": s.slug,
            "name_en": s.name_en,
            "name_zh": s.name_zh,
            "current_role": s.current_role,
            "h_index": s.h_index,
        }
        for s in students_rows
    ]

    # papers (most recent first)
    papers = list(
        db.execute(
            select(Paper, PaperAuthor.position)
            .join(PaperAuthor, PaperAuthor.paper_id == Paper.id)
            .where(PaperAuthor.researcher_id == r.id)
            .order_by(desc(Paper.first_seen_at))
            .limit(80)
        ).all()
    )

    paper_topics_map: dict[int, list[str]] = {}
    if papers:
        topic_rows = db.execute(
            select(PaperTopic.paper_id, Topic.slug)
            .join(Topic, Topic.id == PaperTopic.topic_id)
            .where(PaperTopic.paper_id.in_([p.id for p, _ in papers]))
        ).all()
        for pid, slug_ in topic_rows:
            paper_topics_map.setdefault(pid, []).append(slug_)

    signature_paper = None
    if r.signature_paper_id:
        sp = db.execute(select(Paper).where(Paper.id == r.signature_paper_id)).scalar_one_or_none()
        if sp:
            signature_paper = _paper_summary(sp, paper_topics_map.get(sp.id, []))

    return {
        **_serialize_full(r),
        "current_affiliation": affiliation,
        "advisor": advisor,
        "inferred_advisors": inferred_advisors,
        "students": students,
        "signature_paper": signature_paper,
        "papers": [
            {
                **_paper_summary(p, paper_topics_map.get(p.id, [])),
                "position": int(pos),
            }
            for p, pos in papers
        ],
    }


def _serialize_summary(r: Researcher) -> dict:
    return {
        "slug": r.slug,
        "name_en": r.name_en,
        "name_zh": r.name_zh,
        "name_zh_source": r.name_zh_source,
        "current_role": r.current_role,
        "country": r.country,
        # Provenance markers — the UI uses these to render an "inferred" vs
        # "verified" badge so the user can spot-check what to trust.
        "country_source": r.country_source,
        "role_source": r.role_source,
        "affiliation_source": r.affiliation_source,
        "confidence_level": r.confidence_level,
        "h_index": r.h_index,
        "citation_count": r.citation_count,
        "works_count": r.works_count,
        "tags": r.tags or [],
        "projects": r.projects or [],
        "bio": r.bio,
        "homepage_url": r.homepage_url,
    }


def _serialize_full(r: Researcher) -> dict:
    return {
        **_serialize_summary(r),
        "email": r.email,
        "twitter_handle": r.twitter_handle,
        "github_handle": r.github_handle,
        "zhihu_url": r.zhihu_url,
        "linkedin_url": r.linkedin_url,
        "photo_url": r.photo_url,
        "career_stage_year": r.career_stage_year,
        "graduation_year_estimate": r.graduation_year_estimate,
        "bio_zh": r.bio_zh,
        "openalex_id": r.openalex_id,
        "orcid": r.orcid,
        "person_score": r.person_score,
        "trajectory_score": r.trajectory_score,
        "investability_score": r.investability_score,
        "investability_score_v2": r.investability_score_v2,
        # Deep-dive freshness — UI shows "深挖于 YYYY-MM-DD · N 源命中" badge
        "deep_dive_run_at": r.deep_dive_run_at.isoformat() if r.deep_dive_run_at else None,
        "deep_dive_sources_used": r.deep_dive_sources_used or {},
    }


def _paper_summary(p: Paper, topics: list[str]) -> dict:
    return {
        "arxiv_id": p.arxiv_id,
        "title": p.title,
        "abstract": p.abstract,
        "venue": p.venue,
        "published_at": p.published_at.isoformat() if p.published_at else None,
        "first_seen_at": p.first_seen_at.isoformat() if p.first_seen_at else None,
        "citation_count": p.citation_count,
        "topics": topics,
        "author_emails": p.author_emails or [],
    }
