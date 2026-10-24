"""Add open-incident fingerprints, occurrence counts and correlation groups."""
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "f34a7c2d9e10"
down_revision: str | Sequence[str] | None = "d02fa541b6e3"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("ALTER TYPE activitytype ADD VALUE IF NOT EXISTS 'OCCURRENCE_DETECTED'")
    op.execute("ALTER TYPE activitytype ADD VALUE IF NOT EXISTS 'INCIDENT_CORRELATED'")
    op.create_table(
        "incident_groups",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("root_service", sa.String(255), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.func.now()),
    )
    op.add_column("incidents", sa.Column("fingerprint", sa.String(64), nullable=True))
    op.add_column(
        "incidents", sa.Column("occurrence_count", sa.Integer(), nullable=False,
                                server_default="1")
    )
    op.add_column(
        "incidents", sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=False,
                                server_default=sa.func.now())
    )
    op.add_column("incidents", sa.Column("service", sa.String(255), nullable=True))
    op.add_column("incidents", sa.Column("request_id", sa.String(255), nullable=True))
    op.add_column("incidents", sa.Column("upstream_name", sa.String(255), nullable=True))
    op.add_column(
        "incidents",
        sa.Column("group_id", sa.Integer(), sa.ForeignKey("incident_groups.id"), nullable=True),
    )
    op.create_index(
        "uq_incidents_open_fingerprint",
        "incidents",
        ["fingerprint"],
        unique=True,
        postgresql_where=sa.text("status IN ('OPEN', 'INVESTIGATING')"),
    )
    op.create_index("ix_incidents_request_id", "incidents", ["request_id"])
    op.create_index("ix_incidents_upstream_name", "incidents", ["upstream_name"])
    op.alter_column("incidents", "occurrence_count", server_default=None)
    op.alter_column("incidents", "last_seen_at", server_default=None)


def downgrade() -> None:
    op.drop_index("ix_incidents_upstream_name", table_name="incidents")
    op.drop_index("ix_incidents_request_id", table_name="incidents")
    op.drop_index("uq_incidents_open_fingerprint", table_name="incidents")
    op.drop_column("incidents", "group_id")
    op.drop_column("incidents", "upstream_name")
    op.drop_column("incidents", "request_id")
    op.drop_column("incidents", "service")
    op.drop_column("incidents", "last_seen_at")
    op.drop_column("incidents", "occurrence_count")
    op.drop_column("incidents", "fingerprint")
    op.drop_table("incident_groups")
