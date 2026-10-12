from datetime import datetime

from pydantic import BaseModel, ConfigDict

from app.models.activity import ActivityType


class ActivityResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    incident_id: int
    user_id: int | None
    activity_type: ActivityType
    detail: str | None
    created_at: datetime
