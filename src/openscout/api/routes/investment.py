"""Investment Lens endpoint — the user's three-pillar ranking.

  GET /investment/picks?limit=10&window_days=30

Returns the top-N researchers by `investability_score_v2` with the paper that
drove the score plus a structured "why" breakdown (breakthrough / commercial /
buzz pillar scores + the reason tokens captured at scoring time).

Designed to power the "Investment Lens · Today's Picks" home-page section.
"""

from fastapi import APIRouter, Query

from ...scraper.work_scoring import top_investment_picks

router = APIRouter()


@router.get("/picks")
def picks(
    limit: int = Query(10, ge=1, le=50),
    window_days: int = Query(30, ge=1, le=365),
    max_per_paper: int = Query(2, ge=1, le=5),
) -> dict:
    """Top investment picks with per-pillar reasoning."""
    items = top_investment_picks(limit=limit, window_days=window_days, max_per_paper=max_per_paper)
    return {
        "window_days": window_days,
        "count": len(items),
        "picks": items,
    }
