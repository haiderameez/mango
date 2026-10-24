"""Add service ingest keys, append-only log records and detection rules."""
from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "d02fa541b6e3"
down_revision: str | Sequence[str] | None = "b1c2d3e4f5a6"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "service_keys",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("service", sa.String(255), nullable=False),
        sa.Column("key_hash", sa.String(255), nullable=False, unique=True),
        sa.Column("created_by", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.func.now()),
    )
    op.create_index("ix_service_keys_service", "service_keys", ["service"])

    op.create_table(
        "log_records",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("service", sa.String(255), nullable=False),
        sa.Column("level", sa.String(32), nullable=False),
        sa.Column("message", sa.String(1000), nullable=False),
        sa.Column("context", postgresql.JSONB(astext_type=sa.Text()), nullable=False,
                  server_default=sa.text("'{}'::jsonb")),
        sa.Column("request_id", sa.String(255), nullable=True),
        sa.Column("ts", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_log_records_ts_brin", "log_records", ["ts"], postgresql_using="brin")
    op.create_index(
        "ix_log_records_context_gin", "log_records", ["context"], postgresql_using="gin"
    )
    op.create_index("ix_log_records_service_ts", "log_records", ["service", "ts"])
    op.create_index("ix_log_records_level", "log_records", ["level"])
    op.create_index("ix_log_records_request_id", "log_records", ["request_id"])

    op.create_table(
        "detection_rules",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("service", sa.String(255), nullable=False, server_default="*"),
        sa.Column("level", sa.String(32), nullable=False),
        sa.Column("threshold", sa.Float(), nullable=False),
        sa.Column("window_seconds", sa.Integer(), nullable=False),
        sa.Column("pattern", sa.String(255), nullable=False, server_default=""),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.true()),
    )
    rules = sa.table(
        "detection_rules",
        sa.column("service", sa.String),
        sa.column("level", sa.String),
        sa.column("threshold", sa.Float),
        sa.column("window_seconds", sa.Integer),
        sa.column("pattern", sa.String),
        sa.column("active", sa.Boolean),
    )
    op.bulk_insert(rules, [
        {"service": "*", "level": "ERROR", "threshold": 5,
         "window_seconds": 60, "pattern": "", "active": True},
        {"service": "*", "level": "*", "threshold": 1,
         "window_seconds": 60, "pattern": "CRITICAL|OutOfMemory", "active": True},
        {"service": "*", "level": "*", "threshold": 5,
         "window_seconds": 300, "pattern": "error_rate", "active": True},
    ])


def downgrade() -> None:
    op.drop_table("detection_rules")
    op.drop_index("ix_log_records_request_id", table_name="log_records")
    op.drop_index("ix_log_records_level", table_name="log_records")
    op.drop_index("ix_log_records_service_ts", table_name="log_records")
    op.drop_index("ix_log_records_context_gin", table_name="log_records")
    op.drop_index("ix_log_records_ts_brin", table_name="log_records")
    op.drop_table("log_records")
    op.drop_index("ix_service_keys_service", table_name="service_keys")
    op.drop_table("service_keys")
