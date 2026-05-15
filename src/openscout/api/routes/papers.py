from datetime import date as Date
from datetime import timedelta

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import desc, func, select
from sqlalchemy.orm import Session

from ...db import get_db
from ...models import Paper

router = APIRouter()


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
