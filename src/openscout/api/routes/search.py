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
    type: str | None = Query(
        None,
        description="optional filter: 'tag' = match against researcher tag labels only",
    ),
) -> dict:
    """Cross-entity search. Returns researchers + papers + matching tag labels.

    When `type=tag`, only researchers whose ANY tag.label contains `q`
    (case-insensitive) are returned; papers + name-match are skipped.
    """
    like = f"%{q}%"

    # `type=tag`: pure tag-label search, Python-side filter (works on every DB).
    if type == "tag":
        target = q.casefold()
        all_tagged = (
            db.execute(select(Researcher).where(Researcher.tags.is_not(None))).scalars().all()
        )
        hits: list[Researcher] = []
        for r in all_tagged:
            for t in r.tags or []:
                tl = t.get("label")
                if tl and target in tl.casefold():
                    hits.append(r)
                    break
        hits.sort(
            key=lambda r: (
                -(r.investability_score_v2 or 0.0),
                -(r.citation_count or 0),
            )
        )
        return {
            "query": q,
            "type": "tag",
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
                    "investability_score_v2": r.investability_score_v2,
                    "tags": [
                        t
                        for t in (r.tags or [])
                        if t.get("label") and target in t["label"].casefold()
                    ][:5],
                }
                for r in hits[:limit]
            ],
            "matched_via_tags": [],
            "papers": [],
        }

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
        .order_by(desc(Researcher.citation_count).nulls_last(), desc(n_papers))
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
