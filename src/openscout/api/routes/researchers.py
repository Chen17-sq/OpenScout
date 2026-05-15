from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from ...db import get_db
from ...models import Researcher

router = APIRouter()


@router.get("/")
def list_researchers(
    db: Session = Depends(get_db),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    stage: str | None = Query(None, description="phd / postdoc / incoming_ap / ap / senior"),
) -> list[dict]:
    stmt = select(Researcher).order_by(Researcher.person_score.desc().nullslast())
    if stage:
        stmt = stmt.where(Researcher.current_role == stage)
    stmt = stmt.limit(limit).offset(offset)
    rows = db.execute(stmt).scalars().all()
    return [_serialize(r) for r in rows]


@router.get("/{slug}")
def get_researcher(slug: str, db: Session = Depends(get_db)) -> dict:
    r = db.execute(select(Researcher).where(Researcher.slug == slug)).scalar_one_or_none()
    if not r:
        raise HTTPException(404, detail=f"researcher {slug!r} not found")
    return _serialize(r)


def _serialize(r: Researcher) -> dict:
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
