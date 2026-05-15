"""Search endpoint — researcher + paper + tag fuzzy match."""

from fastapi import APIRouter, Depends, Query
from sqlalchemy import desc, func, or_, select
from sqlalchemy.orm import Session

from ...db import get_db
from ...models import Paper, PaperAuthor, Researcher

router = APIRouter()


@router.get("/")
def search(
    q: str = Query(..., min_length=1, description="search term"),
    db: Session = Depends(get_db),
    limit: int = Query(15, ge=1, le=50),
) -> dict:
    """Cross-entity search. Returns researchers + papers + matching tag labels."""
    like = f"%{q}%"

    # Researchers — by name or tag label
    n_papers = func.count(PaperAuthor.paper_id).label("n")
    r_stmt = (
        select(Researcher, n_papers)
        .outerjoin(PaperAuthor, PaperAuthor.researcher_id == Researcher.id)
        .where(
            or_(
                Researcher.name_en.ilike(like),
                Researcher.name_zh.ilike(like),
                Researcher.bio.ilike(like),
            )
        )
        .group_by(Researcher.id)
        .order_by(desc(Researcher.citation_count.nullslast()), desc(n_papers))
        .limit(limit)
    )
    researcher_rows = db.execute(r_stmt).all()

    # Also surface researchers whose JSON tags include the term (SQLite JSON1 LIKE).
    # We grep the raw JSON string — works for both 'tags' (research directions) and 'projects'.
    tag_stmt = (
        select(Researcher)
        .where(
            or_(
                func.cast(Researcher.tags, type_=func.text(0).type).ilike(like),
                func.cast(Researcher.projects, type_=func.text(0).type).ilike(like),
            )
        )
        .limit(limit)
    )
    try:
        tagged = list(db.execute(tag_stmt).scalars().all())
    except Exception:
        tagged = []  # cast/json LIKE not portable to all DBs; degrade gracefully

    # Papers — by title or abstract substring
    p_stmt = (
        select(Paper)
        .where(or_(Paper.title.ilike(like), Paper.abstract.ilike(like)))
        .order_by(desc(Paper.first_seen_at))
        .limit(limit)
    )
    paper_rows = list(db.execute(p_stmt).scalars().all())

    return {
        "query": q,
        "researchers": [
            {
                "slug": r.slug,
                "name_en": r.name_en,
                "name_zh": r.name_zh,
                "current_role": r.current_role,
                "country": r.country,
                "confidence_level": r.confidence_level,
                "h_index": r.h_index,
                "citation_count": r.citation_count,
                "n_papers": int(n),
                "tags": (r.tags or [])[:5],
            }
            for r, n in researcher_rows
        ],
        "matched_via_tags": [
            {"slug": r.slug, "name_en": r.name_en, "name_zh": r.name_zh}
            for r in tagged
            if r.slug not in {x.slug for x, _ in researcher_rows}
        ][:5],
        "papers": [
            {
                "arxiv_id": p.arxiv_id,
                "title": p.title,
                "first_seen_at": p.first_seen_at.isoformat() if p.first_seen_at else None,
            }
            for p in paper_rows
        ],
    }
