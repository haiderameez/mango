import enum
from datetime import UTC, datetime

from sqlalchemy import DateTime, ForeignKey, Index, String
from sqlalchemy import Enum as SQLEnum
from sqlalchemy.orm import Mapped, mapped_column

from app.database.base import Base


class ActivityType(enum.Enum):
    INCIDENT_CREATED = "INCIDENT_CREATED"
    ASSIGNED = "ASSIGNED"
    REASSIGNED = "REASSIGNED"
    STATUS_CHANGED = "STATUS_CHANGED"
    COMMENT_ADDED = "COMMENT_ADDED"
    INVESTIGATION_STARTED = "INVESTIGATION_STARTED"
    INVESTIGATION_COMPLETED = "INVESTIGATION_COMPLETED"
    INVESTIGATION_FAILED = "INVESTIGATION_FAILED"


class Activity(Base):
    """Append-only record of a meaningful event on an incident. Never updated or deleted."""

    __tablename__ = "activities"
    __table_args__ = (Index("ix_activities_incident_id_created_at", "incident_id", "created_at"),)

    id: Mapped[int] = mapped_column(primary_key=True)

    incident_id: Mapped[int] = mapped_column(
        ForeignKey("incidents.id", ondelete="CASCADE"), nullable=False, index=True
    )

    # NULL actor = system-generated event (e.g. the AI investigation).
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)

    activity_type: Mapped[ActivityType] = mapped_column(SQLEnum(ActivityType), nullable=False)

    detail: Mapped[str | None] = mapped_column(String(500), nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        nullable=False,
    )
