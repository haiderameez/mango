"""create activities, workflow_runs and agent_executions tables

Revision ID: b1c2d3e4f5a6
Revises: a65fa45b5bdf
Create Date: 2026-10-12 00:00:00.000000

"""
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "b1c2d3e4f5a6"
down_revision: str | Sequence[str] | None = "a65fa45b5bdf"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

ACTIVITY_TYPE = sa.Enum(
    "INCIDENT_CREATED",
    "ASSIGNED",
    "REASSIGNED",
    "STATUS_CHANGED",
    "COMMENT_ADDED",
    "INVESTIGATION_STARTED",
    "INVESTIGATION_COMPLETED",
    "INVESTIGATION_FAILED",
    name="activitytype",
)

RUN_STATUS = sa.Enum("PENDING", "RUNNING", "COMPLETED", "FAILED", name="runstatus")


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "activities",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("incident_id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=True),
        sa.Column("activity_type", ACTIVITY_TYPE, nullable=False),
        sa.Column("detail", sa.String(length=500), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["incident_id"], ["incidents.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_activities_incident_id", "activities", ["incident_id"])
    op.create_index(
        "ix_activities_incident_id_created_at", "activities", ["incident_id", "created_at"]
    )

    op.create_table(
        "workflow_runs",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("incident_id", sa.Integer(), nullable=False),
        sa.Column("status", RUN_STATUS, nullable=False),
        sa.Column("triggered_by", sa.String(length=100), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("error", sa.String(length=1000), nullable=True),
        sa.Column("report", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["incident_id"], ["incidents.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_workflow_runs_incident_id", "workflow_runs", ["incident_id"])

    op.create_table(
        "agent_executions",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("workflow_run_id", sa.Integer(), nullable=False),
        sa.Column("agent_name", sa.String(length=100), nullable=False),
        sa.Column("status", RUN_STATUS, nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("output", sa.JSON(), nullable=True),
        sa.Column("error", sa.String(length=1000), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["workflow_run_id"], ["workflow_runs.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_agent_executions_workflow_run_id", "agent_executions", ["workflow_run_id"])


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_table("agent_executions")
    op.drop_table("workflow_runs")
    op.drop_table("activities")
    RUN_STATUS.drop(op.get_bind(), checkfirst=True)
    ACTIVITY_TYPE.drop(op.get_bind(), checkfirst=True)
