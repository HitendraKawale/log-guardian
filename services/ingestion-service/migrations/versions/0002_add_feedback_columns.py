"""add feedback columns to logs

Revision ID: 0002
Revises: 0001
Create Date: 2026-06-20
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("logs", sa.Column("true_label", sa.Boolean(), nullable=True))
    op.add_column("logs", sa.Column("feedback_at", sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    op.drop_column("logs", "feedback_at")
    op.drop_column("logs", "true_label")
