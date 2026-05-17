"""Tag aggregation endpoints — typed tag system (topic / institution / signal).

Each `Researcher.tags` entry is `{label, score, level, type, source?, label_zh?, country?}`.
Legacy entries (pre-v1.10) lack `type` and are treated as `topic` for grouping.
"""

from collections import Counter
from typing import Any

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from ...db import get_db
from ...models import Researcher

router = APIRouter()


def _tag_type(t: dict) -> str:
    """Return the tag's type; legacy untyped tags default to 'topic'."""
    return t.get("type") or "topic"


def _load_tagged_researchers(db: Session) -> list[Researcher]:
    return list(db.execute(select(Researcher).where(Researcher.tags.is_not(None))).scalars().all())


@router.get("")
@router.get("/")
def list_tags(
    db: Session = Depends(get_db),
    per_type_limit: int = Query(50, ge=1, le=500),
) -> dict[str, list[dict]]:
    """All distinct tags grouped by type, sorted by count desc.

    Returns `{signal: [...], institution: [...], topic: [...]}`.
    Top `per_type_limit` per group (default 50).
    """
    rs = _load_tagged_researchers(db)

    # Bucket counts + carry-along metadata (label_zh, country, level) per (type, label).
    counts: dict[tuple[str, str], int] = Counter()
    meta: dict[tuple[str, str], dict[str, Any]] = {}

    for r in rs:
        for t in r.tags or []:
            label = t.get("label")
            if not label:
                continue
            ttype = _tag_type(t)
            key = (ttype, label)
            counts[key] += 1
            existing = meta.get(key)
            if existing is None:
                meta[key] = {
                    "label_zh": t.get("label_zh"),
                    "country": t.get("country"),
                    "level": int(t.get("level", 0) or 0),
                }
            else:
                # Keep first non-null value for each field; max level.
                if existing.get("label_zh") is None and t.get("label_zh"):
                    existing["label_zh"] = t.get("label_zh")
                if existing.get("country") is None and t.get("country"):
                    existing["country"] = t.get("country")
                lvl = int(t.get("level", 0) or 0)
                if lvl > existing["level"]:
                    existing["level"] = lvl

    grouped: dict[str, list[dict]] = {"signal": [], "institution": [], "topic": []}
    for (ttype, label), n in counts.items():
        m = meta[(ttype, label)]
        entry: dict[str, Any] = {"label": label, "count": n}
        # Include label_zh only when present — keeps payload tidy.
        if m.get("label_zh"):
            entry["label_zh"] = m["label_zh"]
        if ttype == "institution" and m.get("country"):
            entry["country"] = m["country"]
        if ttype == "topic":
            entry["level"] = m["level"]
        grouped.setdefault(ttype, []).append(entry)

    for ttype in grouped:
        grouped[ttype].sort(key=lambda x: (-x["count"], x["label"]))
        grouped[ttype] = grouped[ttype][:per_type_limit]

    return grouped


@router.get("/{label}")
def researchers_by_tag(
    label: str,
    db: Session = Depends(get_db),
    limit: int = Query(100, ge=1, le=500),
) -> dict:
    """Researchers tagged with exactly `label` (case-insensitive equality).

    Sort: investability_score_v2 desc (nulls last), then name_en asc. Limit 100.
    """
    rs = _load_tagged_researchers(db)

    matched: list[Researcher] = []
    matched_type: str | None = None
    target = label.casefold()
    for r in rs:
        for t in r.tags or []:
            tl = t.get("label")
            if tl and tl.casefold() == target:
                matched.append(r)
                if matched_type is None:
                    matched_type = _tag_type(t)
                break

    def sort_key(r: Researcher) -> tuple[float, str]:
        # Negate score so higher comes first; None → +inf so they sink to bottom.
        score = r.investability_score_v2
        score_key = -score if score is not None else float("inf")
        return (score_key, (r.name_en or "").casefold())

    matched.sort(key=sort_key)

    return {
        "label": label,
        "type": matched_type,
        "count": len(matched),
        "researchers": [
            {
                "slug": r.slug,
                "name_en": r.name_en,
                "name_zh": r.name_zh,
                "country": r.country,
                "current_role": r.current_role,
                "h_index": r.h_index,
                "investability_score_v2": r.investability_score_v2,
            }
            for r in matched[:limit]
        ],
    }
