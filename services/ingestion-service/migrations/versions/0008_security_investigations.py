"""Bind one investigation to a saved case without rebuilding its journal's parent table."""

import sqlalchemy as sa
from alembic import op

revision = "0008"
down_revision = "0007"
branch_labels = None
depends_on = None


def upgrade():
    if op.get_bind().dialect.name == "sqlite":
        op.execute(
            "ALTER TABLE investigations ADD COLUMN security_case_id VARCHAR(36) REFERENCES security_cases(id) ON DELETE RESTRICT"
        )
    else:
        op.add_column("investigations", sa.Column("security_case_id", sa.String(36), nullable=True))
        op.create_foreign_key(
            "fk_investigations_security_case",
            "investigations",
            "security_cases",
            ["security_case_id"],
            ["id"],
            ondelete="RESTRICT",
        )
    op.create_index(
        "ix_investigations_security_case_id", "investigations", ["security_case_id"], unique=True
    )


def downgrade():
    if (
        op.get_bind()
        .execute(sa.text("SELECT 1 FROM investigations WHERE security_case_id IS NOT NULL LIMIT 1"))
        .first()
    ):
        raise RuntimeError("cannot downgrade linked security investigations")
    op.drop_index("ix_investigations_security_case_id", table_name="investigations")
    if op.get_bind().dialect.name != "sqlite":
        op.drop_constraint("fk_investigations_security_case", "investigations", type_="foreignkey")
    op.drop_column("investigations", "security_case_id")
