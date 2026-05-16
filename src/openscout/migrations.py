"""Lightweight schema migrations for SQLite.

We don't (yet) use Alembic. For the v0 single-DB-file deployment, this script
runs idempotent `ALTER TABLE ... ADD COLUMN` statements. Errors from a column
already existing are swallowed silently — it's the only failure mode for an
ADD COLUMN that we don't want to halt on.

Called from `openscout init-db` after `Base.metadata.create_all`.
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
    ("institutions", "openalex_id", "TEXT"),
    ("papers", "openalex_id", "TEXT"),
    ("papers", "influential_citation_count", "INTEGER"),
    ("papers", "concepts", "TEXT"),
    ("papers", "author_emails", "TEXT"),
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
