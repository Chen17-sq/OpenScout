"""Per-step freshness gate for the daily orchestrator.

The `openscout daily` orchestrator runs ~25 steps. Some are wasteful to repeat
every day:
  - faculty page diff: only matters Jan-May / Oct-Nov, and never twice in a week
  - conference PC: changes a few times a year
  - awards roster: changes after a conference, otherwise static
  - lineage inference: idempotent + slow; useful when there are >50 new papers
  - banner: only needs re-render when tracked/papers totals move

This module gives `cli_daily._step()` a tiny "did we run this recently?" gate.
Backed by the `step_log` table (see `models.StepLog`): one row per step name,
upserted on every run. We never grow this table — same name → same row.

Status values stored:
  - "ok"      — step ran successfully (this gates `should_skip`)
  - "failed"  — step raised; we still record so the dashboard can read it
  - "skipped" — step was skipped (by freshness OR --skip flag); recorded so
                a daily-run log shows the skip reason

Only "ok" rows count for freshness — if the last run failed, we WILL retry
next time even if it's within `min_hours`.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import select

from ..db import session_scope
from ..models import StepLog


def record(step_name: str, status: str, result: Any | None = None) -> None:
    """Upsert the row for `step_name` with the latest run.

    `result` is best-effort serialised: dicts/lists pass through, anything
    else (a typer Exit, an int counter, None) is wrapped/coerced so callers
    don't have to think about it.
    """
    payload = _coerce_result(result)
    with session_scope() as db:
        row = db.execute(select(StepLog).where(StepLog.step_name == step_name)).scalar_one_or_none()
        if row is None:
            row = StepLog(
                step_name=step_name,
                last_status=status,
                last_result_json=payload,
            )
            db.add(row)
        else:
            row.last_status = status
            row.last_result_json = payload
            # last_run_at uses onupdate=func.now(); SQLite needs an explicit
            # touch since onupdate only fires when *other* columns change AND
            # the connection sees a server-default. Easiest: set it ourselves.
            row.last_run_at = datetime.now(UTC)


def last_run(step_name: str) -> datetime | None:
    """Return the timestamp of the last recorded run (any status), or None."""
    with session_scope() as db:
        row = db.execute(select(StepLog).where(StepLog.step_name == step_name)).scalar_one_or_none()
        if row is None:
            return None
        return _ensure_aware(row.last_run_at)


def should_skip(step_name: str, min_hours: float) -> bool:
    """True if the last OK run was less than `min_hours` ago.

    Only "ok" rows gate skipping — failed/skipped runs do NOT block a retry.
    A missing row (never run) is NEVER skipped.
    """
    if min_hours <= 0:
        return False
    with session_scope() as db:
        row = db.execute(select(StepLog).where(StepLog.step_name == step_name)).scalar_one_or_none()
        if row is None or row.last_status != "ok":
            return False
        last = _ensure_aware(row.last_run_at)
        return (datetime.now(UTC) - last) < timedelta(hours=min_hours)


def last_result(step_name: str) -> dict | None:
    """Return the last recorded `result` payload for a step, or None."""
    with session_scope() as db:
        row = db.execute(select(StepLog).where(StepLog.step_name == step_name)).scalar_one_or_none()
        if row is None:
            return None
        return row.last_result_json


# ── internal helpers ────────────────────────────────────────────────────────


def _coerce_result(result: Any) -> dict | None:
    """Make `result` safe to store in the JSON column.

    Steps return wildly different shapes: dicts of counts, ints, None, or
    sometimes a Path object. We wrap non-dict/list values as {"value": str(x)}.
    """
    if result is None:
        return None
    if isinstance(result, dict):
        return _stringify_unknowns(result)
    if isinstance(result, list):
        return {"value": result}
    if isinstance(result, int | float | str | bool):
        return {"value": result}
    return {"value": str(result)}


def _stringify_unknowns(d: dict) -> dict:
    """Replace non-JSON values in a dict with str() — best effort, never raises."""
    out: dict = {}
    for k, v in d.items():
        if isinstance(v, dict):
            out[str(k)] = _stringify_unknowns(v)
        elif isinstance(v, list | int | float | str | bool) or v is None:
            out[str(k)] = v
        else:
            out[str(k)] = str(v)
    return out


def _ensure_aware(ts: datetime) -> datetime:
    """SQLite drops tzinfo; force-attach UTC so comparisons don't blow up."""
    if ts.tzinfo is None:
        return ts.replace(tzinfo=UTC)
    return ts
