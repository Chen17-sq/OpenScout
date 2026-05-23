"""step log

Revision ID: a1b2c3d4e5f6
Revises: 90d04f63fc49
Create Date: 2026-05-23 00:00:00.000000

Adds the `step_log` table — per-step freshness gate for the daily
orchestrator. See `openscout/scraper/step_log.py` and `cli_daily.py`'s
`_step()` wrapper for how this is consumed.

Schema-only migration: no data backfill. The orchestrator populates rows
on first daily run.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "a1b2c3d4e5f6"
down_revision: str | Sequence[str] | None = "90d04f63fc49"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "step_log",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("step_name", sa.String(length=128), nullable=False),
        sa.Column(
            "last_run_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("(CURRENT_TIMESTAMP)"),
            nullable=False,
        ),
        sa.Column("last_status", sa.String(length=16), nullable=False),
        sa.Column("last_result_json", sa.JSON(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    with op.batch_alter_table("step_log", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_step_log_step_name"), ["step_name"], unique=True)


def downgrade() -> None:
    """Downgrade schema."""
    with op.batch_alter_table("step_log", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_step_log_step_name"))
    op.drop_table("step_log")
