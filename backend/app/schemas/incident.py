from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.models.incident import SeverityLevel, StatusLevel


class IncidentCreate(BaseModel):
    title: str = Field(min_length=1, max_length=255)
    description: str | None = Field(default=None, max_length=1000)
    severity: SeverityLevel


class IncidentResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    title: str
    description: str | None
    severity: SeverityLevel
    status: StatusLevel
    created_by: int
    assigned_to: int | None
    created_at: datetime
    updated_at: datetime


class IncidentAssign(BaseModel):
    assigned_to: int


class IncidentStatusUpdate(BaseModel):
    status: StatusLevel


class IncidentFilters(BaseModel):
    """Query parameters for listing incidents. limit/offset pagination, newest first."""

    status: StatusLevel | None = None
    severity: SeverityLevel | None = None
    assigned_to: int | None = None
    created_by: int | None = None
    search: str | None = Field(default=None, max_length=255)
    limit: int = Field(default=20, ge=1, le=100)
    offset: int = Field(default=0, ge=0)
