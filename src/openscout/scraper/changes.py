"""Record researcher-field changes as Signal rows.

When OpenAlex enrichment updates a researcher's h-index / citation_count /
affiliation / tags, write a Signal row capturing the delta. The frontend can
then show a per-researcher activity timeline.

This is called from inside enrichment functions OR run as a periodic
"detect_changes" pass that diffs current values against a previous snapshot.
For v0 we use the periodic approach so the existing enricher code stays simple.
"""

from datetime import UTC, datetime

from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from ..db import session_scope
from ..models import Researcher, Signal

_TRACKED_FIELDS = ("h_index", "citation_count", "works_count", "country", "current_role")


def record_change(
    db: Session,
    researcher_id: int,
    field: str,
    old_value,
    new_value,
    source: str = "enrichment",
) -> None:
    """Insert a Signal row capturing a field-level change."""
    db.add(
        Signal(
            researcher_id=researcher_id,
            type="field_change",
            payload={
                "field": field,
                "old": old_value,
                "new": new_value,
            },
            source=source,
            occurred_at=datetime.now(UTC),
        )
    )


def detect_changes_since(snapshot: dict[int, dict]) -> dict[str, int]:
    """Diff each Researcher row's tracked fields against a snapshot.

    snapshot: {researcher_id: {field: value, ...}}
    """
    counts = {"signals_added": 0}
    with session_scope() as db:
        rs = list(db.execute(select(Researcher)).scalars().all())
        for r in rs:
            prev = snapshot.get(r.id, {})
            for f in _TRACKED_FIELDS:
                old = prev.get(f)
                new = getattr(r, f, None)
                if old != new and old is not None and new is not None:
                    record_change(db, r.id, f, old, new)
                    counts["signals_added"] += 1
    return counts


def take_snapshot() -> dict[int, dict]:
    """Capture {researcher_id: {field: value}} for all tracked fields."""
    with session_scope() as db:
        rs = list(db.execute(select(Researcher)).scalars().all())
        return {r.id: {f: getattr(r, f) for f in _TRACKED_FIELDS} for r in rs}


def recent_signals(researcher_id: int, limit: int = 20) -> list[dict]:
    """Return recent Signal rows for one researcher."""
    with session_scope() as db:
        rows = list(
            db.execute(
                select(Signal)
                .where(Signal.researcher_id == researcher_id)
                .order_by(desc(Signal.detected_at))
                .limit(limit)
            )
            .scalars()
            .all()
        )
        return [
            {
                "type": s.type,
                "payload": s.payload,
                "occurred_at": s.occurred_at.isoformat() if s.occurred_at else None,
                "detected_at": s.detected_at.isoformat() if s.detected_at else None,
                "source": s.source,
            }
            for s in rows
        ]
