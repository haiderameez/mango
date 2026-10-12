import enum
from datetime import UTC, datetime

from sqlalchemy import JSON, DateTime, ForeignKey, String, Text
from sqlalchemy import Enum as SQLEnum
from sqlalchemy.orm import Mapped, mapped_column

from app.database.base import Base


class RunStatus(enum.Enum):
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"


class WorkflowRun(Base):
    """One AI investigation of one incident."""

    __tablename__ = "workflow_runs"

    id: Mapped[int] = mapped_column(primary_key=True)

    incident_id: Mapped[int] = mapped_column(
        ForeignKey("incidents.id", ondelete="CASCADE"), nullable=False, index=True
    )

    status: Mapped[RunStatus] = mapped_column(
        SQLEnum(RunStatus), nullable=False, default=RunStatus.PENDING
    )

    # Who/what asked for this run, e.g. "user:3" or "dummycommerce".
    triggered_by: Mapped[str] = mapped_column(String(100), nullable=False)

    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    error: Mapped[str | None] = mapped_column(String(1000), nullable=True)

    report: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC), nullable=False
    )

    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
        nullable=False,
    )


class AgentExecution(Base):
    """One node of the investigation graph, as it actually ran."""

    __tablename__ = "agent_executions"

    id: Mapped[int] = mapped_column(primary_key=True)

    workflow_run_id: Mapped[int] = mapped_column(
        ForeignKey("workflow_runs.id", ondelete="CASCADE"), nullable=False, index=True
    )

    agent_name: Mapped[str] = mapped_column(String(100), nullable=False)

    status: Mapped[RunStatus] = mapped_column(SQLEnum(RunStatus), nullable=False)

    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # The node's own structured output. Prompts and secrets are deliberately not stored.
    output: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    error: Mapped[str | None] = mapped_column(String(1000), nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC), nullable=False
    )
