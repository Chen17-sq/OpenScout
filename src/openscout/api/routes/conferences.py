"""Conference endpoint — group papers by venue (ICLR / NeurIPS / ICML / arXiv)."""

from fastapi import APIRouter, Depends
from sqlalchemy import desc, func, select
from sqlalchemy.orm import Session

from ...db import get_db
from ...models import Paper, PaperAuthor, Researcher

router = APIRouter()


@router.get("/")
def list_conferences(db: Session = Depends(get_db)) -> list[dict]:
    """All distinct venues + paper counts + oral/spotlight subcount."""
    venue_count = func.count(Paper.id).label("n")
    stmt = (
        select(Paper.venue, venue_count)
        .where(Paper.venue.is_not(None))
        .group_by(Paper.venue)
        .order_by(desc(venue_count))
    )
    return [{"venue": v, "n_papers": int(n)} for v, n in db.execute(stmt).all()]


@router.get("/by-prefix/{prefix}")
def papers_by_venue_prefix(prefix: str, db: Session = Depends(get_db)) -> dict:
    """Papers whose venue starts with the prefix (e.g. 'ICLR 2025')."""
    rows = list(
        db.execute(
            select(Paper)
            .where(Paper.venue.ilike(f"{prefix}%"))
            .order_by(desc(Paper.buzz_score), desc(Paper.first_seen_at))
            .limit(200)
        )
        .scalars()
        .all()
    )

    out = []
    for p in rows:
        first_author = db.execute(
            select(Researcher)
            .join(PaperAuthor, PaperAuthor.researcher_id == Researcher.id)
            .where(PaperAuthor.paper_id == p.id, PaperAuthor.position == 1)
            .limit(1)
        ).scalar_one_or_none()
        out.append(
            {
                "arxiv_id": p.arxiv_id,
                "title": p.title,
                "abstract": p.abstract,
                "venue": p.venue,
                "first_seen_at": p.first_seen_at.isoformat() if p.first_seen_at else None,
                "buzz_score": p.buzz_score,
                "first_author": (
                    {
                        "slug": first_author.slug,
                        "name_en": first_author.name_en,
                        "name_zh": first_author.name_zh,
                    }
                    if first_author
                    else None
                ),
            }
        )
    return {"prefix": prefix, "n": len(out), "papers": out}
