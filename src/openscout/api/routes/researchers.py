from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import desc, func, or_, select
from sqlalchemy.orm import Session

from ...db import get_db
from ...models import Institution, Paper, PaperAuthor, PaperTopic, Researcher, Topic

router = APIRouter()


@router.get("/")
def list_researchers(
    db: Session = Depends(get_db),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    stage: str | None = Query(None, description="phd / postdoc / incoming_ap / ap / senior"),
    confidence: str | None = Query(None, description="low / medium / high"),
    topic: str | None = Query(None, description="topic slug"),
    q: str | None = Query(None, description="search by name (case-insensitive substring)"),
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
    if q:
        base = base.where(or_(Researcher.name_en.ilike(f"%{q}%"), Researcher.name_zh.ilike(f"%{q}%")))
    if topic:
        topic_row = db.execute(select(Topic).where(Topic.slug == topic)).scalar_one_or_none()
        if topic_row:
            base = base.join(PaperTopic, PaperTopic.paper_id == PaperAuthor.paper_id).where(
                PaperTopic.topic_id == topic_row.id
            )

    total = int(db.execute(select(func.count()).select_from(base.subquery())).scalar() or 0)

    stmt = (
        base.order_by(
            desc(n_papers),
            Researcher.confidence_level == "low",  # anchors first
            Researcher.name_en,
        )
        .limit(limit)
        .offset(offset)
    )
    rows = db.execute(stmt).all()
    return {
        "total": total,
        "limit": limit,
        "offset": offset,
        "items": [
            {**_serialize_researcher(r), "n_papers": int(n)} for r, n in rows
        ],
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
            affiliation = {"name": inst.name, "name_zh": inst.name_zh, "country": inst.country}

    advisor = None
    if r.advisor_id:
        adv = db.execute(
            select(Researcher).where(Researcher.id == r.advisor_id)
        ).scalar_one_or_none()
        if adv:
            advisor = {"slug": adv.slug, "name_en": adv.name_en, "name_zh": adv.name_zh}

    # papers (most recent first)
    papers = list(
        db.execute(
            select(Paper, PaperAuthor.position)
            .join(PaperAuthor, PaperAuthor.paper_id == Paper.id)
            .where(PaperAuthor.researcher_id == r.id)
            .order_by(desc(Paper.first_seen_at))
            .limit(50)
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

    return {
        **_serialize_researcher(r),
        "current_affiliation": affiliation,
        "advisor": advisor,
        "papers": [
            {
                "arxiv_id": p.arxiv_id,
                "title": p.title,
                "abstract": p.abstract,
                "venue": p.venue,
                "published_at": p.published_at.isoformat() if p.published_at else None,
                "first_seen_at": p.first_seen_at.isoformat() if p.first_seen_at else None,
                "position": int(pos),
                "topics": paper_topics_map.get(p.id, []),
            }
            for p, pos in papers
        ],
    }


def _serialize_researcher(r: Researcher) -> dict:
    return {
        "slug": r.slug,
        "name_en": r.name_en,
        "name_zh": r.name_zh,
        "email": r.email,
        "homepage_url": r.homepage_url,
        "twitter_handle": r.twitter_handle,
        "github_handle": r.github_handle,
        "zhihu_url": r.zhihu_url,
        "current_role": r.current_role,
        "career_stage_year": r.career_stage_year,
        "graduation_year_estimate": r.graduation_year_estimate,
        "bio": r.bio,
        "bio_zh": r.bio_zh,
        "person_score": r.person_score,
        "trajectory_score": r.trajectory_score,
        "investability_score": r.investability_score,
        "confidence_level": r.confidence_level,
    }
