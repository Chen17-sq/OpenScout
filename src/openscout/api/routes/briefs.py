from datetime import date as Date

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from ...db import get_db
from ...models import DailyBrief

router = APIRouter()


@router.get("/latest")
def latest_brief(db: Session = Depends(get_db)) -> dict:
    b = db.execute(
        select(DailyBrief).order_by(desc(DailyBrief.brief_date)).limit(1)
    ).scalar_one_or_none()
    if not b:
        raise HTTPException(404, detail="no briefs yet — run `openscout brief`")
    return _serialize(b)


@router.get("/{brief_date}")
def get_brief(brief_date: str, db: Session = Depends(get_db)) -> dict:
    try:
        parsed = Date.fromisoformat(brief_date)
    except ValueError as exc:
        raise HTTPException(400, detail="brief_date must be YYYY-MM-DD") from exc
    b = db.execute(
        select(DailyBrief).where(DailyBrief.brief_date == parsed)
    ).scalar_one_or_none()
    if not b:
        raise HTTPException(404, detail=f"no brief for {brief_date}")
    return _serialize(b)


def _serialize(b: DailyBrief) -> dict:
    return {
        "brief_date": b.brief_date.isoformat(),
        "volume": b.volume,
        "issue": b.issue,
        "rendered_md": b.rendered_md,
        "generated_at": b.generated_at.isoformat() if b.generated_at else None,
    }
