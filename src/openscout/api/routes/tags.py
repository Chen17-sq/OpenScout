"""Tag aggregation endpoints — top research directions across the roster."""

from collections import Counter

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from ...db import get_db
from ...models import Researcher

router = APIRouter()


@router.get("/")
def list_tags(
    db: Session = Depends(get_db),
    limit: int = Query(40, ge=1, le=200),
    min_count: int = Query(2, ge=1),
) -> list[dict]:
    """All distinct research-direction tags + how many researchers have each."""
    rows = list(
        db.execute(select(Researcher.tags).where(Researcher.tags.is_not(None))).scalars().all()
    )
    counter: Counter[str] = Counter()
    score_sum: dict[str, float] = {}
    levels: dict[str, int] = {}
    for tags in rows:
        if not tags:
            continue
        for t in tags:
            label = t.get("label")
            if not label:
                continue
            counter[label] += 1
            score_sum[label] = score_sum.get(label, 0.0) + float(t.get("score", 0) or 0)
            levels[label] = max(levels.get(label, 0), int(t.get("level", 0) or 0))

    out = [
        {
            "label": label,
            "count": n,
            "avg_score": round(score_sum[label] / n, 3) if n else 0.0,
            "level": levels.get(label, 0),
        }
        for label, n in counter.most_common()
        if n >= min_count
    ]
    return out[:limit]


@router.get("/{label}")
def researchers_by_tag(label: str, db: Session = Depends(get_db), limit: int = 30) -> list[dict]:
    """Researchers whose tag list contains `label` (case-sensitive substring of JSON)."""
    rs = (
        db.execute(select(Researcher).where(Researcher.tags.is_not(None)))
        .scalars()
        .all()
    )
    matched: list[dict] = []
    for r in rs:
        if not r.tags:
            continue
        if any((t.get("label") or "").lower() == label.lower() for t in r.tags):
            matched.append(
                {
                    "slug": r.slug,
                    "name_en": r.name_en,
                    "name_zh": r.name_zh,
                    "current_role": r.current_role,
                    "country": r.country,
                    "confidence_level": r.confidence_level,
                    "h_index": r.h_index,
                    "citation_count": r.citation_count,
                }
            )
    matched.sort(key=lambda x: -(x["citation_count"] or 0))
    return matched[:limit]
