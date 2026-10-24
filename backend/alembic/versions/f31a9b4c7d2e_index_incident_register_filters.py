"""Index filtered incident register ordering."""
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "f31a9b4c7d2e"
down_revision: str | Sequence[str] | None = "e18c44b7a9f2"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_index(
        "ix_incidents_status_severity_created_at",
        "incidents",
        ["status", "severity", sa.text("created_at DESC"), sa.text("id DESC")],
    )


def downgrade() -> None:
    op.drop_index("ix_incidents_status_severity_created_at", table_name="incidents")
