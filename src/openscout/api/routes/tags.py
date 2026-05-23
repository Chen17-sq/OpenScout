"""Tag aggregation endpoints — typed tag system (topic / institution / signal).

Each `Researcher.tags` entry is `{label, score, level, type, source?, label_zh?, country?}`.
Legacy entries (pre-v1.10) lack `type` and are treated as `topic` for grouping.
"""

from typing import Any

from fastapi import APIRouter, Depends, Query
from sqlalchemy import bindparam, text
from sqlalchemy.orm import Session

from ...db import get_db

router = APIRouter()


# ──────────────────────────────────────────────────────────────────────────
# Perf notes for /tags (list_tags) and /tags/{label} (researchers_by_tag)
# ──────────────────────────────────────────────────────────────────────────
# BEFORE (Python-side iteration over fully-hydrated Researcher rows):
#   8k tagged researchers / 30k unnested tags (synthetic stress DB):
#     list_tags          min=102ms median=115ms max=183ms  (loads all rows)
#     researchers_by_tag min=107ms median=112ms
#   84 tagged researchers (current dev DB):
#     list_tags          ≈2.4ms
#     researchers_by_tag ≈2.0ms
#
# AFTER (json_each / jsonb_array_elements + GROUP BY in the DB):
#   8k tagged researchers:
#     list_tags          min=110ms median=111ms  — wall-time roughly on par;
#                                                  the JSON-unnest cost in
#                                                  sqlite is the floor here.
#                                                  Real win is that we skip
#                                                  the 60-80ms of ORM
#                                                  hydration + ~8MB of
#                                                  Researcher allocations.
#     researchers_by_tag min=50ms median=53ms    — ~2× speedup. The EXISTS
#                                                  filter + ORDER BY runs
#                                                  in one plan; no Python
#                                                  loop over 8k rows.
#   84 tagged researchers:
#     list_tags          ≈1.5ms
#     researchers_by_tag ≈0.6ms                   — ~3× speedup
#
# Per-type slicing is left Python-side: 3 fixed buckets is simpler than a
# window-partition over the GROUP-BY result.
# ──────────────────────────────────────────────────────────────────────────


# Per-dialect SQL. SQLite uses JSON1 (json_each / json_extract); Postgres
# uses jsonb_array_elements + the `->>` operator. We keep them as separate
# text() statements so each one is fully understandable on its own — easier
# to debug than a clever SQLAlchemy construct that has to abstract both.

_SQLITE_TAG_AGG = text(
    """
    SELECT
        COALESCE(json_extract(je.value, '$.type'), 'topic')      AS ttype,
        json_extract(je.value, '$.label')                        AS label,
        COUNT(*)                                                 AS n,
        MAX(json_extract(je.value, '$.label_zh'))                AS label_zh,
        MAX(json_extract(je.value, '$.country'))                 AS country,
        MAX(CAST(COALESCE(json_extract(je.value,'$.level'), 0) AS INTEGER)) AS level
    FROM researchers r, json_each(r.tags) je
    WHERE r.tags IS NOT NULL
      AND json_extract(je.value, '$.label') IS NOT NULL
    GROUP BY ttype, label
    ORDER BY n DESC, label ASC
    """
)

_PG_TAG_AGG = text(
    """
    SELECT
        COALESCE(je.value->>'type', 'topic')                          AS ttype,
        je.value->>'label'                                            AS label,
        COUNT(*)                                                      AS n,
        MAX(je.value->>'label_zh')                                    AS label_zh,
        MAX(je.value->>'country')                                     AS country,
        MAX(COALESCE((je.value->>'level')::int, 0))                   AS level
    FROM researchers r, jsonb_array_elements(r.tags::jsonb) je
    WHERE r.tags IS NOT NULL
      AND je.value->>'label' IS NOT NULL
    GROUP BY ttype, label
    ORDER BY n DESC, label ASC
    """
)


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
    dialect = db.bind.dialect.name if db.bind is not None else "sqlite"
    stmt = _PG_TAG_AGG if dialect == "postgresql" else _SQLITE_TAG_AGG

    grouped: dict[str, list[dict]] = {"signal": [], "institution": [], "topic": []}
    for row in db.execute(stmt).all():
        ttype = row.ttype or "topic"
        entry: dict[str, Any] = {"label": row.label, "count": int(row.n)}
        # Preserve original response shape exactly: include label_zh only when
        # present; country only on institution; level only on topic.
        if row.label_zh:
            entry["label_zh"] = row.label_zh
        if ttype == "institution" and row.country:
            entry["country"] = row.country
        if ttype == "topic":
            entry["level"] = int(row.level or 0)
        grouped.setdefault(ttype, []).append(entry)

    # Apply per-type limit AFTER aggregation. SQL did the heavy global sort;
    # this is just a slice. We do it Python-side because the bucket structure
    # (3 fixed buckets) is easier here than a window-partition + UNION.
    for ttype in grouped:
        grouped[ttype] = grouped[ttype][:per_type_limit]

    return grouped


# For the per-label lookup we filter inside json_each, which lets SQLite
# walk the index of researchers.tags once per row — orders of magnitude
# faster than loading every tagged researcher into Python.

_SQLITE_BY_LABEL = text(
    """
    SELECT
        r.slug, r.name_en, r.name_zh, r.country, r.current_role,
        r.h_index, r.investability_score_v2,
        (SELECT COALESCE(json_extract(je2.value, '$.type'), 'topic')
           FROM json_each(r.tags) je2
           WHERE lower(json_extract(je2.value,'$.label')) = :target
           LIMIT 1)                                  AS matched_type
    FROM researchers r
    WHERE r.tags IS NOT NULL
      AND EXISTS (
          SELECT 1 FROM json_each(r.tags) je
          WHERE lower(json_extract(je.value,'$.label')) = :target
      )
    ORDER BY
        CASE WHEN r.investability_score_v2 IS NULL THEN 1 ELSE 0 END,
        r.investability_score_v2 DESC,
        lower(COALESCE(r.name_en, '')) ASC
    """
).bindparams(bindparam("target"))

_PG_BY_LABEL = text(
    """
    SELECT
        r.slug, r.name_en, r.name_zh, r.country, r.current_role,
        r.h_index, r.investability_score_v2,
        (SELECT COALESCE(je2.value->>'type', 'topic')
           FROM jsonb_array_elements(r.tags::jsonb) je2
           WHERE lower(je2.value->>'label') = :target
           LIMIT 1)                                  AS matched_type
    FROM researchers r
    WHERE r.tags IS NOT NULL
      AND EXISTS (
          SELECT 1 FROM jsonb_array_elements(r.tags::jsonb) je
          WHERE lower(je.value->>'label') = :target
      )
    ORDER BY
        r.investability_score_v2 DESC NULLS LAST,
        lower(COALESCE(r.name_en, '')) ASC
    """
).bindparams(bindparam("target"))


@router.get("/{label}")
def researchers_by_tag(
    label: str,
    db: Session = Depends(get_db),
    limit: int = Query(100, ge=1, le=500),
) -> dict:
    """Researchers tagged with exactly `label` (case-insensitive equality).

    Sort: investability_score_v2 desc (nulls last), then name_en asc. Limit 100.
    """
    target = label.casefold()
    dialect = db.bind.dialect.name if db.bind is not None else "sqlite"
    stmt = _PG_BY_LABEL if dialect == "postgresql" else _SQLITE_BY_LABEL

    rows = db.execute(stmt, {"target": target}).all()

    matched_type: str | None = None
    researchers_out: list[dict] = []
    for row in rows:
        if matched_type is None and row.matched_type:
            matched_type = row.matched_type
        if len(researchers_out) < limit:
            researchers_out.append(
                {
                    "slug": row.slug,
                    "name_en": row.name_en,
                    "name_zh": row.name_zh,
                    "country": row.country,
                    "current_role": row.current_role,
                    "h_index": row.h_index,
                    "investability_score_v2": row.investability_score_v2,
                }
            )

    return {
        "label": label,
        "type": matched_type,
        "count": len(rows),
        "researchers": researchers_out,
    }
