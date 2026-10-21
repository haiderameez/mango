"""Add RBAC, acknowledgement, and escalation policies."""
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "d7a8b9c0e123"
down_revision: str | Sequence[str] | None = "c3f4a8d2e611"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "users", sa.Column("role", sa.String(16), nullable=False, server_default="responder")
    )
    op.alter_column("users", "role", server_default=None)
    op.create_check_constraint(
        "ck_users_role", "users", "role IN ('admin', 'responder', 'viewer')"
    )
    op.add_column("incidents", sa.Column("acknowledged_at", sa.DateTime(timezone=True)))
    op.add_column("incidents", sa.Column("escalated_at", sa.DateTime(timezone=True)))
    op.execute("ALTER TYPE activitytype ADD VALUE IF NOT EXISTS 'INCIDENT_ACKNOWLEDGED'")
    op.execute("ALTER TYPE activitytype ADD VALUE IF NOT EXISTS 'INCIDENT_ESCALATED'")
    op.create_table(
        "escalation_policies",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("severity", sa.String(16), nullable=False),
        sa.Column("delay_minutes", sa.Integer(), nullable=False),
        sa.Column("escalate_to_user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.alter_column("escalation_policies", "enabled", server_default=None)


def downgrade() -> None:
    op.drop_table("escalation_policies")
    op.drop_column("incidents", "escalated_at")
    op.drop_column("incidents", "acknowledged_at")
    op.drop_column("users", "role")
