"""Institution endpoints — list + per-institution roster."""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import desc, func, select
from sqlalchemy.orm import Session

from ...db import get_db
from ...models import Institution, Researcher

router = APIRouter()


@router.get("/")
def list_institutions(db: Session = Depends(get_db)) -> list[dict]:
    """All seed institutions + researcher counts + aggregate citation."""
    n_researchers = func.count(Researcher.id).label("n")
    total_cites = func.coalesce(func.sum(Researcher.citation_count), 0).label("c")
    stmt = (
        select(Institution, n_researchers, total_cites)
        .outerjoin(Researcher, Researcher.current_affiliation_id == Institution.id)
        .group_by(Institution.id)
        .order_by(desc(n_researchers))
    )
    return [
        {
            "id": i.id,
            "name": i.name,
            "name_zh": i.name_zh,
            "country": i.country,
            "type": i.type,
            "homepage_url": i.homepage_url,
            "openalex_id": i.openalex_id,
            "n_researchers": int(n),
            "total_citations": int(c),
        }
        for i, n, c in db.execute(stmt).all()
    ]


@router.get("/{inst_id}")
def get_institution(inst_id: int, db: Session = Depends(get_db)) -> dict:
    inst = db.execute(select(Institution).where(Institution.id == inst_id)).scalar_one_or_none()
    if not inst:
        raise HTTPException(404, detail=f"institution {inst_id} not found")

    researchers = list(
        db.execute(
            select(Researcher)
            .where(Researcher.current_affiliation_id == inst.id)
            .order_by(desc(Researcher.citation_count).nulls_last())
        )
        .scalars()
        .all()
    )

    return {
        "id": inst.id,
        "name": inst.name,
        "name_zh": inst.name_zh,
        "country": inst.country,
        "type": inst.type,
        "homepage_url": inst.homepage_url,
        "openalex_id": inst.openalex_id,
        "researchers": [
            {
                "slug": r.slug,
                "name_en": r.name_en,
                "name_zh": r.name_zh,
                "current_role": r.current_role,
                "h_index": r.h_index,
                "citation_count": r.citation_count,
                "tags": (r.tags or [])[:3],
            }
            for r in researchers
        ],
    }
