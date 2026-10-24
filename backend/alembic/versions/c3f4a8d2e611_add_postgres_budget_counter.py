"""Store daily model request budgets in the database."""
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "c3f4a8d2e611"
down_revision: str | Sequence[str] | None = "f34a7c2d9e10"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "daily_llm_budgets",
        sa.Column("quota_date", sa.String(10), primary_key=True),
        sa.Column("used", sa.Integer(), nullable=False, server_default="0"),
    )
    op.alter_column("daily_llm_budgets", "used", server_default=None)


def downgrade() -> None:
    op.drop_table("daily_llm_budgets")
