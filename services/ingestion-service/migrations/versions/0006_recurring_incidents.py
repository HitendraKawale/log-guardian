"""Allow later incidents without losing prior candidate review or investigation links."""

import sqlalchemy as sa
from alembic import op

revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "detector_states",
        sa.Column("service", sa.String(128), primary_key=True),
        sa.Column("data", sa.JSON(), nullable=False),
    )
    op.add_column(
        "investigation_candidates", sa.Column("active_service", sa.String(128), nullable=True)
    )
    op.add_column(
        "investigation_candidates",
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "investigation_candidates",
        sa.Column("occurrence_count", sa.Integer(), nullable=False, server_default="1"),
    )
    op.add_column(
        "investigation_candidates",
        sa.Column("signal_details", sa.JSON(), nullable=False, server_default="{}"),
    )
    table = sa.table(
        "investigation_candidates",
        sa.column("occurred_at"),
        sa.column("last_seen_at"),
        sa.column("signal_details", sa.JSON()),
    )
    op.execute(
        table.update().values(
            last_seen_at=table.c.occurred_at,
            signal_details={"reasons": ["unseen-template"], "legacy": True},
        )
    )
    op.drop_index("ix_candidates_service_template", table_name="investigation_candidates")
    op.create_index(
        "ix_candidates_service_template", "investigation_candidates", ["service", "template"]
    )
    op.create_index(
        "ix_candidates_active_service", "investigation_candidates", ["active_service"], unique=True
    )


def downgrade():
    duplicate = (
        op.get_bind()
        .execute(
            sa.text(
                "SELECT 1 FROM investigation_candidates GROUP BY service, template HAVING COUNT(*) > 1 LIMIT 1"
            )
        )
        .first()
    )
    if duplicate:
        raise RuntimeError("cannot downgrade recurring candidate history to lifetime uniqueness")
    op.drop_index("ix_candidates_active_service", table_name="investigation_candidates")
    op.drop_index("ix_candidates_service_template", table_name="investigation_candidates")
    op.create_index(
        "ix_candidates_service_template",
        "investigation_candidates",
        ["service", "template"],
        unique=True,
    )
    with op.batch_alter_table("investigation_candidates") as batch:
        for name in ("signal_details", "occurrence_count", "last_seen_at", "active_service"):
            batch.drop_column(name)
    op.drop_table("detector_states")
