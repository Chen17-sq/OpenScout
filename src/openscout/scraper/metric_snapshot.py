"""Daily researcher metric snapshots — the data behind trend sparklines.

The investor question this answers: "is this person *rising*?" Current
values (h_index / citation_count / investability_v2) only say where someone
is today; the `metric_snapshots` table records where they were every day so
the profile page can draw a 90-day trend line.

Scope: only researchers with investability_score_v2 > 0 get snapshotted —
snapshotting all 12k+ rows daily would bloat SQLite for no value (the
unscored tail is mostly auto-discovered co-authors nobody looks at).

Idempotency: keyed on (researcher_id, snapshot_date). Re-running the daily
pipeline on the same day overwrites that day's rows instead of duplicating,
so a crashed-and-retried run is harmless.

Runs as the `metric snapshots (trends)` step in `cli_daily.py`, right after
the investability_v2 rollup so today's row captures the fresh score.
"""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import select

from ..db import session_scope
from ..models import MetricSnapshot, Researcher


def take_snapshots() -> dict:
    """Upsert today's (researcher_id, date) snapshot rows. Returns counts."""
    today = datetime.now(UTC).date().isoformat()
    inserted = 0
    updated = 0

    with session_scope() as db:
        researchers = (
            db.execute(select(Researcher).where(Researcher.investability_score_v2 > 0))
            .scalars()
            .all()
        )

        # One query for today's existing rows — re-runs update in place.
        existing: dict[int, MetricSnapshot] = {
            row.researcher_id: row
            for row in db.execute(
                select(MetricSnapshot).where(MetricSnapshot.snapshot_date == today)
            ).scalars()
        }

        for r in researchers:
            row = existing.get(r.id)
            if row is None:
                db.add(
                    MetricSnapshot(
                        researcher_id=r.id,
                        snapshot_date=today,
                        h_index=r.h_index,
                        citation_count=r.citation_count,
                        works_count=r.works_count,
                        investability_v2=r.investability_score_v2,
                    )
                )
                inserted += 1
            else:
                row.h_index = r.h_index
                row.citation_count = r.citation_count
                row.works_count = r.works_count
                row.investability_v2 = r.investability_score_v2
                updated += 1

    return {
        "date": today,
        "inserted": inserted,
        "updated": updated,
        "snapshotted": inserted + updated,
    }
