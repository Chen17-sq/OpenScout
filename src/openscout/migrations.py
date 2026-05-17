"""Lightweight schema migrations for SQLite.

Dual-path schema management
---------------------------
For SQLite (local + small deploys) we use this module — idempotent
`ALTER TABLE ... ADD COLUMN` runs. No version table, no rollbacks.
Errors from "column already exists" are swallowed silently — it's the
only failure mode for an ADD COLUMN that we don't want to halt on.
This keeps the SQLite story zero-friction: clone, `init-db`, done.

For Postgres (prod scale) we use Alembic instead — see
`src/openscout/alembic/`. Alembic carries proper version history and
reversible migrations, which matter once a DB has irreplaceable rows.

Both paths are dispatched from `openscout init-db` (see `cli.py`):
the CLI branches on the `DATABASE_URL` prefix.
"""

from sqlalchemy import text
from sqlalchemy.engine import Engine
from sqlalchemy.exc import OperationalError

# (table, column, type) — append-only. Once shipped, do not edit a row in place;
# add a new row for any subsequent change.
COLUMNS: list[tuple[str, str, str]] = [
    ("researchers", "openalex_id", "TEXT"),
    ("researchers", "name_zh_source", "TEXT"),
    ("researchers", "country", "TEXT"),
    ("researchers", "h_index", "INTEGER"),
    ("researchers", "citation_count", "INTEGER"),
    ("researchers", "works_count", "INTEGER"),
    ("researchers", "tags", "TEXT"),
    ("researchers", "projects", "TEXT"),
    ("researchers", "signature_paper_id", "INTEGER"),
    ("researchers", "country_source", "TEXT"),
    ("researchers", "role_source", "TEXT"),
    ("researchers", "affiliation_source", "TEXT"),
    ("researchers", "investability_score_v2", "REAL"),
    ("researchers", "deep_dive_run_at", "TIMESTAMP"),
    ("researchers", "deep_dive_sources_used", "TEXT"),
    ("institutions", "openalex_id", "TEXT"),
    ("papers", "openalex_id", "TEXT"),
    ("papers", "influential_citation_count", "INTEGER"),
    ("papers", "concepts", "TEXT"),
    ("papers", "author_emails", "TEXT"),
    ("papers", "breakthrough_score", "REAL"),
    ("papers", "commercial_score", "REAL"),
    ("papers", "work_score_reasons", "TEXT"),
]


def _has_column(conn, table: str, col: str) -> bool:
    rows = conn.execute(text(f"PRAGMA table_info({table})")).fetchall()
    return any(r[1] == col for r in rows)


def upgrade_schema(engine: Engine) -> list[str]:
    """Returns the list of column-strings actually added."""
    added: list[str] = []
    with engine.begin() as conn:
        for table, col, ty in COLUMNS:
            if _has_column(conn, table, col):
                continue
            try:
                conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {col} {ty}"))
                added.append(f"{table}.{col}")
            except OperationalError:
                # Already exists / table doesn't yet exist; harmless.
                pass
    return added
