"""Investment Lens endpoint — the user's three-pillar ranking.

  GET /investment/picks?limit=10&window_days=30
  GET /investment/picks.csv?limit=50&window_days=30

Returns the top-N researchers by `investability_score_v2` with the paper that
drove the score plus a structured "why" breakdown (breakthrough / commercial /
buzz pillar scores + the reason tokens captured at scoring time).

Designed to power the "Investment Lens · Today's Picks" home-page section.
"""

from __future__ import annotations

import csv
import io
from collections.abc import Iterator
from datetime import UTC, datetime

from fastapi import APIRouter, Query
from fastapi.responses import StreamingResponse
from sqlalchemy import select

from ...db import session_scope
from ...models import Paper, Researcher
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


def _signal_labels_from_tags(tags: list[dict] | None) -> list[str]:
    """Pull the `type=signal` labels out of a Researcher.tags JSON list."""
    if not tags:
        return []
    out: list[str] = []
    for t in tags:
        if not isinstance(t, dict):
            continue
        if t.get("type") == "signal":
            label = t.get("label")
            if label:
                out.append(str(label))
    return out


def _picks_to_csv_rows(items: list[dict]) -> list[dict]:
    """Enrich picks with the extra researcher/paper fields needed in the CSV.

    `top_investment_picks` returns a slim shape (no h_index, citation_count,
    works_count, work_score, signal_tags). The CSV needs them, so we do a
    second pass to fetch them in bulk — one extra round-trip rather than
    refactoring the scoring function's return shape.
    """
    if not items:
        return []
    slugs = [p["slug"] for p in items]
    arxiv_ids = [p["top_paper"]["arxiv_id"] for p in items if p.get("top_paper")]
    with session_scope() as db:
        r_rows = db.execute(select(Researcher).where(Researcher.slug.in_(slugs))).scalars().all()
        r_by_slug = {r.slug: r for r in r_rows}
        p_rows = (
            db.execute(select(Paper).where(Paper.arxiv_id.in_(arxiv_ids))).scalars().all()
            if arxiv_ids
            else []
        )
        p_by_arxiv = {p.arxiv_id: p for p in p_rows}

        enriched: list[dict] = []
        for rank, pick in enumerate(items, start=1):
            r = r_by_slug.get(pick["slug"])
            tp = pick.get("top_paper") or {}
            paper = p_by_arxiv.get(tp.get("arxiv_id")) if tp.get("arxiv_id") else None
            signal_labels = _signal_labels_from_tags(r.tags if r else None)
            enriched.append(
                {
                    "rank": rank,
                    "slug": pick["slug"],
                    "name_en": pick.get("name_en") or "",
                    "name_zh": pick.get("name_zh") or "",
                    "country": pick.get("country") or "",
                    "current_role": pick.get("current_role") or "",
                    "h_index": r.h_index if r and r.h_index is not None else "",
                    "citation_count": r.citation_count
                    if r and r.citation_count is not None
                    else "",
                    "works_count": r.works_count if r and r.works_count is not None else "",
                    "investability_v2": (
                        f"{pick['score']:.4f}" if pick.get("score") is not None else ""
                    ),
                    "top_paper_title": tp.get("title") or "",
                    "top_paper_arxiv_id": tp.get("arxiv_id") or "",
                    "breakthrough_score": (
                        f"{tp['breakthrough']:.4f}" if tp.get("breakthrough") is not None else ""
                    ),
                    "commercial_score": (
                        f"{tp['commercial']:.4f}" if tp.get("commercial") is not None else ""
                    ),
                    "buzz_score": (f"{tp['buzz']:.4f}" if tp.get("buzz") is not None else ""),
                    "work_score": (
                        f"{paper.work_score:.4f}" if paper and paper.work_score is not None else ""
                    ),
                    "signal_tags": ";".join(signal_labels),
                    "reasons": ";".join(tp.get("reasons") or []),
                }
            )
        return enriched


_CSV_COLUMNS = [
    "rank",
    "slug",
    "name_en",
    "name_zh",
    "country",
    "current_role",
    "h_index",
    "citation_count",
    "works_count",
    "investability_v2",
    "top_paper_title",
    "top_paper_arxiv_id",
    "breakthrough_score",
    "commercial_score",
    "buzz_score",
    "work_score",
    "signal_tags",
    "reasons",
]


@router.get("/picks.csv")
def picks_csv(
    limit: int = Query(50, ge=1, le=50),
    window_days: int = Query(30, ge=1, le=365),
    max_per_paper: int = Query(2, ge=1, le=5),
) -> StreamingResponse:
    """CSV export of top investment picks — same params as /picks, default
    limit=50 so the download is meaty. Streamed via StreamingResponse so the
    response starts before the whole body is built.
    """
    items = top_investment_picks(limit=limit, window_days=window_days, max_per_paper=max_per_paper)
    rows = _picks_to_csv_rows(items)

    def _iter() -> Iterator[str]:
        buf = io.StringIO()
        writer = csv.DictWriter(buf, fieldnames=_CSV_COLUMNS, extrasaction="ignore")
        writer.writeheader()
        yield buf.getvalue()
        buf.seek(0)
        buf.truncate(0)
        for row in rows:
            writer.writerow(row)
            yield buf.getvalue()
            buf.seek(0)
            buf.truncate(0)

    today = datetime.now(UTC).strftime("%Y-%m-%d")
    filename = f"openscout-picks-{today}.csv"
    return StreamingResponse(
        _iter(),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
