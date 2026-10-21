import enum
from datetime import UTC, datetime

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String, text
from sqlalchemy import Enum as SQLEnum
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base import Base
from app.models.user import User


class SeverityLevel(enum.Enum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


class StatusLevel(enum.Enum):
    OPEN = "OPEN"
    INVESTIGATING = "INVESTIGATING"
    RESOLVED = "RESOLVED"


class IncidentGroup(Base):
    __tablename__ = "incident_groups"

    id: Mapped[int] = mapped_column(primary_key=True)
    root_service: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC), nullable=False
    )


class Incident(Base):
    __tablename__ = "incidents"
    __table_args__ = (
        Index(
            "uq_incidents_open_fingerprint",
            "fingerprint",
            unique=True,
            postgresql_where=text("status IN ('OPEN', 'INVESTIGATING')"),
            sqlite_where=text("status IN ('OPEN', 'INVESTIGATING')"),
        ),
        Index("ix_incidents_request_id", "request_id"),
        Index("ix_incidents_upstream_name", "upstream_name"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)

    title: Mapped[str] = mapped_column(String(255), nullable=False)

    description: Mapped[str | None] = mapped_column(String(1000), nullable=True)

    severity: Mapped[SeverityLevel] = mapped_column(
        SQLEnum(SeverityLevel),
        nullable=False,
        default=SeverityLevel.LOW
    )

    status: Mapped[StatusLevel] = mapped_column(
        SQLEnum(StatusLevel),
        nullable=False,
        default=StatusLevel.OPEN
    )

    created_by: Mapped[int] = mapped_column(
        ForeignKey("users.id"),
        nullable=False
    )

    assigned_to: Mapped[int | None] = mapped_column(
        ForeignKey("users.id"),
        nullable=True
    )

    fingerprint: Mapped[str | None] = mapped_column(String(64), nullable=True)
    occurrence_count: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    last_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC), nullable=False
    )
    service: Mapped[str | None] = mapped_column(String(255), nullable=True)
    request_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    upstream_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    group_id: Mapped[int | None] = mapped_column(ForeignKey("incident_groups.id"), nullable=True)
    acknowledged_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    escalated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    # Eager, because every incident is read with its people: a lazy load here is the
    # classic N+1 on the register, which is the most-hit endpoint in the product.
    creator: Mapped["User"] = relationship(foreign_keys=[created_by], lazy="joined")
    assignee: Mapped["User | None"] = relationship(foreign_keys=[assigned_to], lazy="joined")

    @property
    def created_by_name(self) -> str:
        return self.creator.name

    @property
    def assigned_to_name(self) -> str | None:
        return self.assignee.name if self.assignee else None

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        nullable=False
    )

    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
        nullable=False
    )
