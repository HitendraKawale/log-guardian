"""Keep immutable security reviews separate from operational and paid investigation rows."""

import sqlalchemy as sa
from alembic import op

revision = "0007"
down_revision = "0006"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "security_cases",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("idempotency_key", sa.String(128), nullable=False, unique=True),
        sa.Column("request_sha256", sa.String(64), nullable=False),
        sa.Column("source_snapshot", sa.JSON(), nullable=False),
        sa.Column("input_hashes", sa.JSON(), nullable=False),
        sa.Column("report", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "security_evidence",
        sa.Column("source_id", sa.String(128), primary_key=True),
        sa.Column("evidence_id", sa.String(128), primary_key=True),
        sa.Column("content_sha256", sa.String(64), nullable=False),
        sa.Column("content", sa.JSON(), nullable=False),
    )


def downgrade():
    if op.get_bind().execute(sa.text("SELECT 1 FROM security_cases LIMIT 1")).first():
        raise RuntimeError("cannot downgrade stored security evidence")
    if op.get_bind().execute(sa.text("SELECT 1 FROM security_evidence LIMIT 1")).first():
        raise RuntimeError("cannot downgrade stored security evidence")
    op.drop_table("security_cases")
    op.drop_table("security_evidence")
