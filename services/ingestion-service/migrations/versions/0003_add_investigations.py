"""add investigation tables and a scope-query index on logs

Revision ID: 0003
Revises: 0002
Create Date: 2026-09-14

Existing log rows and the scoring contract are untouched: this revision only
creates new tables and one additional index.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0003"
down_revision: str | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "investigations",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("question", sa.String(2048), nullable=False),
        sa.Column("system", sa.String(1), nullable=False),
        sa.Column("scope", sa.JSON(), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("error", sa.String(64), nullable=True),
        sa.Column("report", sa.JSON(), nullable=True),
        sa.Column("idempotency_key", sa.String(128), nullable=True, unique=True),
        sa.Column("request_sha256", sa.String(64), nullable=False),
        sa.Column("model_requested", sa.String(64), nullable=True),
        sa.Column("prompt_sha256", sa.String(64), nullable=True),
        sa.Column("code_revision", sa.String(64), nullable=True),
        sa.Column("usage", sa.JSON(), nullable=True),
        sa.Column("estimated_cost_usd", sa.String(32), nullable=True),
        sa.Column("elapsed_ms", sa.Float(), nullable=True),
        sa.Column("worker_id", sa.String(128), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_investigations_status", "investigations", ["status"])
    op.create_table(
        "investigation_events",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "investigation_id",
            sa.String(36),
            sa.ForeignKey("investigations.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("sequence", sa.Integer(), nullable=False),
        sa.Column("kind", sa.String(32), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index(
        "ix_investigation_events_run_seq",
        "investigation_events",
        ["investigation_id", "sequence"],
        unique=True,
    )
    op.create_index("ix_logs_service_timestamp", "logs", ["service", "timestamp"])


def downgrade() -> None:
    op.drop_index("ix_logs_service_timestamp", table_name="logs")
    op.drop_index("ix_investigation_events_run_seq", table_name="investigation_events")
    op.drop_table("investigation_events")
    op.drop_index("ix_investigations_status", table_name="investigations")
    op.drop_table("investigations")
