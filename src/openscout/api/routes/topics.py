"""Topic endpoints — list of topics + per-topic landing page data."""

from datetime import date as Date
from datetime import timedelta

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import desc, func, select
from sqlalchemy.orm import Session

from ...db import get_db
from ...models import Paper, PaperAuthor, PaperTopic, Researcher, Topic

router = APIRouter()


@router.get("/")
def list_topics(db: Session = Depends(get_db)) -> list[dict]:
    """All topics, ordered by paper count."""
    n_papers = func.count(PaperTopic.paper_id).label("n")
    stmt = (
        select(Topic, n_papers)
        .outerjoin(PaperTopic, PaperTopic.topic_id == Topic.id)
        .group_by(Topic.id)
        .order_by(desc(n_papers))
    )
    return [
        {
            "slug": t.slug,
            "name": t.name,
            "name_zh": t.name_zh,
            "description": t.description,
            "n_papers": int(n),
        }
        for t, n in db.execute(stmt).all()
    ]


@router.get("/{slug}")
def get_topic(slug: str, db: Session = Depends(get_db)) -> dict:
    t = db.execute(select(Topic).where(Topic.slug == slug)).scalar_one_or_none()
    if not t:
        raise HTTPException(404, detail=f"topic {slug!r} not found")

    # Recent papers in this topic
    recent_papers_stmt = (
        select(Paper)
        .join(PaperTopic, PaperTopic.paper_id == Paper.id)
        .where(PaperTopic.topic_id == t.id)
        .order_by(desc(Paper.first_seen_at))
        .limit(20)
    )
    recent = list(db.execute(recent_papers_stmt).scalars().all())

    # Top first-authors in this topic
    n_papers = func.count(PaperAuthor.paper_id).label("n")
    top_authors_stmt = (
        select(Researcher, n_papers)
        .join(PaperAuthor, PaperAuthor.researcher_id == Researcher.id)
        .join(PaperTopic, PaperTopic.paper_id == PaperAuthor.paper_id)
        .where(PaperTopic.topic_id == t.id, PaperAuthor.position == 1)
        .group_by(Researcher.id)
        .order_by(desc(n_papers))
        .limit(15)
    )
    authors = list(db.execute(top_authors_stmt).all())

    # 7-day discovery trend
    today = Date.today()
    trend = []
    for offset in range(6, -1, -1):
        d = today - timedelta(days=offset)
        n = int(
            db.execute(
                select(func.count(Paper.id))
                .join(PaperTopic, PaperTopic.paper_id == Paper.id)
                .where(PaperTopic.topic_id == t.id, func.date(Paper.first_seen_at) == d)
            ).scalar()
            or 0
        )
        trend.append({"date": d.isoformat(), "n": n})

    return {
        "slug": t.slug,
        "name": t.name,
        "name_zh": t.name_zh,
        "description": t.description,
        "recent_papers": [
            {
                "arxiv_id": p.arxiv_id,
                "title": p.title,
                "abstract": p.abstract,
                "published_at": p.published_at.isoformat() if p.published_at else None,
                "first_seen_at": p.first_seen_at.isoformat() if p.first_seen_at else None,
            }
            for p in recent
        ],
        "top_first_authors": [
            {
                "slug": r.slug,
                "name_en": r.name_en,
                "name_zh": r.name_zh,
                "current_role": r.current_role,
                "confidence_level": r.confidence_level,
                "n_papers": int(n),
            }
            for r, n in authors
        ],
        "trend_7d": trend,
    }
