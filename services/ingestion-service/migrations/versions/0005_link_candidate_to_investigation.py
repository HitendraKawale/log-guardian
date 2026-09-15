"""link a candidate to the investigation a human promoted it into

Revision ID: 0005
Revises: 0004
Create Date: 2026-09-15

Adds one nullable column. The link doubles as the idempotency record for
promotion: a candidate that already points at an investigation returns that
one rather than queueing a second paid run.

SQLite cannot add a column with a foreign key via ALTER TABLE, so the
constraint is created inside a batch operation, which rewrites the table on
SQLite and is a plain ALTER on Postgres.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0005"
down_revision: str | None = "0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("investigation_candidates") as batch:
        batch.add_column(sa.Column("investigation_id", sa.String(36), nullable=True))
        batch.create_foreign_key(
            "fk_candidates_investigation",
            "investigations",
            ["investigation_id"],
            ["id"],
            ondelete="SET NULL",
        )


def downgrade() -> None:
    with op.batch_alter_table("investigation_candidates") as batch:
        batch.drop_constraint("fk_candidates_investigation", type_="foreignkey")
        batch.drop_column("investigation_id")
