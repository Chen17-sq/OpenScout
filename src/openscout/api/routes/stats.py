"""Stats endpoints — counts, growth, top-N by various dimensions."""

from datetime import date as Date
from datetime import timedelta

from fastapi import APIRouter, Depends
from sqlalchemy import desc, func, select
from sqlalchemy.orm import Session

from ...db import get_db
from ...models import Paper, PaperAuthor, Researcher, Topic

router = APIRouter()


@router.get("/")
def overview(db: Session = Depends(get_db)) -> dict:
    """Topline stats: totals + 7-day series for papers + researchers."""
    tracked = int(db.execute(select(func.count(Researcher.id))).scalar() or 0)
    papers = int(db.execute(select(func.count(Paper.id))).scalar() or 0)
    anchors = int(
        db.execute(
            select(func.count(Researcher.id)).where(Researcher.confidence_level != "low")
        ).scalar()
        or 0
    )
    topics_count = int(db.execute(select(func.count(Topic.id))).scalar() or 0)

    # last 7 days: papers + researchers discovered per day
    today = Date.today()
    series: list[dict] = []
    for offset in range(6, -1, -1):
        d = today - timedelta(days=offset)
        p_n = int(
            db.execute(
                select(func.count(Paper.id)).where(func.date(Paper.first_seen_at) == d)
            ).scalar()
            or 0
        )
        r_n = int(
            db.execute(
                select(func.count(Researcher.id)).where(func.date(Researcher.first_seen_at) == d)
            ).scalar()
            or 0
        )
        series.append({"date": d.isoformat(), "papers": p_n, "researchers": r_n})

    return {
        "totals": {
            "researchers": tracked,
            "anchors": anchors,
            "papers": papers,
            "topics": topics_count,
        },
        "series_7d": series,
    }


@router.get("/top-collaborators")
def top_collaborators(db: Session = Depends(get_db), limit: int = 10) -> list[dict]:
    """Researchers who appear on the most papers (collapsing all positions)."""
    n_papers = func.count(PaperAuthor.paper_id).label("n")
    stmt = (
        select(Researcher, n_papers)
        .join(PaperAuthor, PaperAuthor.researcher_id == Researcher.id)
        .group_by(Researcher.id)
        .order_by(desc(n_papers))
        .limit(limit)
    )
    return [
        {
            "slug": r.slug,
            "name_en": r.name_en,
            "name_zh": r.name_zh,
            "current_role": r.current_role,
            "confidence_level": r.confidence_level,
            "n_papers": int(n),
        }
        for r, n in db.execute(stmt).all()
    ]


@router.get("/by-topic")
def by_topic(db: Session = Depends(get_db)) -> list[dict]:
    """Paper counts grouped by topic slug."""
    from ...models import PaperTopic

    stmt = (
        select(Topic, func.count(PaperTopic.paper_id).label("n"))
        .outerjoin(PaperTopic, PaperTopic.topic_id == Topic.id)
        .group_by(Topic.id)
        .order_by(desc("n"))
    )
    return [
        {
            "slug": t.slug,
            "name": t.name,
            "name_zh": t.name_zh,
            "n_papers": int(n),
        }
        for t, n in db.execute(stmt).all()
    ]
