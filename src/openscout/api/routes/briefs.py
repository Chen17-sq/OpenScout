from dataclasses import asdict
from datetime import date as Date
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from ...brief import data as bd
from ...db import get_db
from ...models import DailyBrief

router = APIRouter()


# ─── Structured (used by the frontend) ──────────────────────────────────────


@router.get("/today")
def brief_today_structured(db: Session = Depends(get_db)) -> dict:
    """Structured brief data for the current day (UTC). Used by the SvelteKit homepage."""
    today = datetime.now(timezone.utc).date()
    brief = bd.collect(db, today)
    return _serialize_brief(brief)


@router.get("/by-date/{brief_date}/structured")
def brief_by_date_structured(brief_date: str, db: Session = Depends(get_db)) -> dict:
    try:
        parsed = Date.fromisoformat(brief_date)
    except ValueError as exc:
        raise HTTPException(400, detail="brief_date must be YYYY-MM-DD") from exc
    brief = bd.collect(db, parsed)
    return _serialize_brief(brief)


# ─── Archive (rendered markdown) ────────────────────────────────────────────


@router.get("/list")
def list_briefs(db: Session = Depends(get_db), limit: int = 30) -> list[dict]:
    rows = (
        db.execute(
            select(DailyBrief).order_by(desc(DailyBrief.brief_date)).limit(limit)
        )
        .scalars()
        .all()
    )
    return [
        {
            "brief_date": r.brief_date.isoformat(),
            "volume": r.volume,
            "issue": r.issue,
            "generated_at": r.generated_at.isoformat() if r.generated_at else None,
        }
        for r in rows
    ]


@router.get("/latest")
def latest_brief(db: Session = Depends(get_db)) -> dict:
    b = db.execute(
        select(DailyBrief).order_by(desc(DailyBrief.brief_date)).limit(1)
    ).scalar_one_or_none()
    if not b:
        raise HTTPException(404, detail="no briefs yet — run `openscout brief`")
    return _serialize_md_brief(b)


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
    return _serialize_md_brief(b)


# ─── Serializers ────────────────────────────────────────────────────────────


def _serialize_md_brief(b: DailyBrief) -> dict:
    return {
        "brief_date": b.brief_date.isoformat(),
        "volume": b.volume,
        "issue": b.issue,
        "rendered_md": b.rendered_md,
        "generated_at": b.generated_at.isoformat() if b.generated_at else None,
    }


def _serialize_brief(brief: bd.BriefData) -> dict:
    return {
        "brief_date": brief.brief_date.isoformat(),
        "issue": brief.issue,
        "kpi": {
            "tracked": brief.tracked,
            "today_papers": brief.today_papers,
            "today_emergences": brief.today_emergences,
            "soon_graduating": brief.soon_graduating,
            "incoming_ap": brief.incoming_ap,
        },
        "new_first_authors": [asdict(s) for s in brief.new_first_authors],
        "anchor_activity": [asdict(s) for s in brief.anchor_activity],
        "soon_graduating_picks": [asdict(s) for s in brief.soon_graduating_picks],
        "incoming_ap_picks": [asdict(s) for s in brief.incoming_ap_picks],
        "hot_papers": [asdict(s) for s in brief.hot_papers],
        "sleeper_picks": [asdict(s) for s in brief.sleeper_picks],
    }
