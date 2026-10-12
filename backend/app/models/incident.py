import enum
from datetime import UTC, datetime

from sqlalchemy import DateTime, ForeignKey, String
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


class Incident(Base):
    __tablename__ = "incidents"

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