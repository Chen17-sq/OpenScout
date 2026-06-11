from datetime import timedelta

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import desc, func, select
from sqlalchemy.orm import Session

from ...db import get_db
from ...models import Paper, PaperAuthor, PaperTopic, Topic

router = APIRouter()


@router.get("/")
def list_papers(
    db: Session = Depends(get_db),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    topic: str | None = Query(None, description="topic slug"),
    has_code: bool | None = Query(None, description="true = only papers with a code link"),
    sort: str = Query("work_score", description="work_score / date / citations / stars"),
) -> dict:
    """Paginated paper index. Same `{total, limit, offset, items}` shape as /researchers/."""
    n_authors = func.count(PaperAuthor.researcher_id).label("n_authors")
    base = (
        select(Paper, n_authors)
        .outerjoin(PaperAuthor, PaperAuthor.paper_id == Paper.id)
        .group_by(Paper.id)
    )

    if has_code is not None:
        base = base.where(Paper.code_url.is_not(None) if has_code else Paper.code_url.is_(None))
    if topic:
        # Unknown slug → no filter (matches /researchers/ behavior).
        topic_row = db.execute(select(Topic).where(Topic.slug == topic)).scalar_one_or_none()
        if topic_row:
            # At most one PaperTopic row per (paper, topic), so the author
            # count in n_authors is not multiplied by this join.
            base = base.join(PaperTopic, PaperTopic.paper_id == Paper.id).where(
                PaperTopic.topic_id == topic_row.id
            )

    total = int(db.execute(select(func.count()).select_from(base.subquery())).scalar() or 0)

    sort_map = {
        "work_score": (desc(Paper.work_score).nulls_last(), desc(Paper.published_at).nulls_last()),
        "date": (desc(Paper.published_at).nulls_last(), desc(Paper.work_score).nulls_last()),
        "citations": (desc(Paper.citation_count), desc(Paper.work_score).nulls_last()),
        "stars": (desc(Paper.github_stars).nulls_last(), desc(Paper.work_score).nulls_last()),
    }
    order_cols = sort_map.get(sort, sort_map["work_score"])
    rows = db.execute(base.order_by(*order_cols).limit(limit).offset(offset)).all()

    # Batch-fetch topic slugs for the page (avoids N+1).
    topics_map: dict[int, list[str]] = {}
    paper_ids = [p.id for p, _ in rows]
    if paper_ids:
        topic_rows = db.execute(
            select(PaperTopic.paper_id, Topic.slug)
            .join(Topic, Topic.id == PaperTopic.topic_id)
            .where(PaperTopic.paper_id.in_(paper_ids))
        ).all()
        for pid, slug in topic_rows:
            topics_map.setdefault(pid, []).append(slug)

    return {
        "total": total,
        "limit": limit,
        "offset": offset,
        "items": [
            {
                "arxiv_id": p.arxiv_id,
                "title": p.title,
                "published_at": p.published_at.isoformat() if p.published_at else None,
                "venue": p.venue,
                "citation_count": p.citation_count,
                "github_stars": p.github_stars,
                "work_score": p.work_score,
                "breakthrough_score": p.breakthrough_score,
                "commercial_score": p.commercial_score,
                "buzz_score": p.buzz_score,
                "topics": topics_map.get(p.id, []),
                "n_authors": int(n),
            }
            for p, n in rows
        ],
    }


@router.get("/today")
def papers_today(db: Session = Depends(get_db)) -> list[dict]:
    """Papers first seen in the last 24 hours, ranked by work_score."""
    cutoff = func.now() - timedelta(days=1)
    rows = (
        db.execute(
            select(Paper)
            .where(Paper.first_seen_at >= cutoff)
            .order_by(desc(Paper.work_score), desc(Paper.first_seen_at))
            .limit(50)
        )
        .scalars()
        .all()
    )
    return [_serialize(p) for p in rows]


@router.get("/{arxiv_id}")
def get_paper(arxiv_id: str, db: Session = Depends(get_db)) -> dict:
    p = db.execute(select(Paper).where(Paper.arxiv_id == arxiv_id)).scalar_one_or_none()
    if not p:
        raise HTTPException(404, detail=f"paper {arxiv_id!r} not found")
    return _serialize(p)


def _serialize(p: Paper) -> dict:
    return {
        "arxiv_id": p.arxiv_id,
        "title": p.title,
        "abstract": p.abstract,
        "one_liner_zh": p.one_liner_zh,
        "published_at": p.published_at.isoformat() if p.published_at else None,
        "venue": p.venue,
        "pdf_url": p.pdf_url,
        "code_url": p.code_url,
        "citation_count": p.citation_count,
        "work_score": p.work_score,
    }
