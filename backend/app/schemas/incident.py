from datetime import datetime

from pydantic import BaseModel, ConfigDict

from app.models.incident import SeverityLevel, StatusLevel

class IncidentCreate(BaseModel):
    title: str
    description: str | None = None
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