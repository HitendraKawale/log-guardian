"""add the investigation candidate queue

Revision ID: 0004
Revises: 0003
Create Date: 2026-09-15

Creates one new table. Existing log rows, the scoring contract and the
investigation tables are untouched.

The unique index on (service, template) is load-bearing rather than tidiness:
the trigger's memory of which templates it has seen is per-process, so a
restart or a second replica re-surfaces a family the first one already raised.
The constraint absorbs those duplicates in the database instead of requiring
every writer to coordinate.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0004"
down_revision: str | None = "0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "investigation_candidates",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("service", sa.String(128), nullable=False),
        sa.Column("level", sa.String(16), nullable=False),
        sa.Column("message", sa.String(), nullable=False),
        sa.Column("template", sa.String(), nullable=False),
        sa.Column("reason", sa.String(32), nullable=False),
        sa.Column("scope", sa.JSON(), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column(
            "log_id",
            sa.Integer(),
            sa.ForeignKey("logs.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("dismissed_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index(
        "ix_candidates_service_template",
        "investigation_candidates",
        ["service", "template"],
        unique=True,
    )
    op.create_index(
        "ix_candidates_status_created",
        "investigation_candidates",
        ["status", "created_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_candidates_status_created", table_name="investigation_candidates")
    op.drop_index("ix_candidates_service_template", table_name="investigation_candidates")
    op.drop_table("investigation_candidates")
