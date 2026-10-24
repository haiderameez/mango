from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class EscalationPolicyCreate(BaseModel):
    severity: Literal["LOW", "MEDIUM", "HIGH", "CRITICAL"] = "CRITICAL"
    delay_minutes: int = Field(default=10, ge=1, le=1440)
    escalate_to_user_id: int


class EscalationPolicyResponse(EscalationPolicyCreate):
    model_config = ConfigDict(from_attributes=True)
    id: int
    enabled: bool
    created_at: datetime


class EscalationPolicyUpdate(BaseModel):
    enabled: bool
