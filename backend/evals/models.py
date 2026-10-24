from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

Category = Literal["dependency", "resource_exhaustion", "code_defect", "config", "latency"]


class IncidentInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: int
    title: str
    description: str
    severity: Literal["LOW", "MEDIUM", "HIGH", "CRITICAL"]
    status: Literal["OPEN"]
    created_at: datetime


class Scenario(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str = Field(pattern=r"^case-\d{2}$")
    family: str
    variant: str
    incident: IncidentInput
    category: Category
    service: str = Field(min_length=1)
    root_cause: str = Field(min_length=1)
    fix: str = Field(min_length=1)

    def answer(self) -> dict:
        return self.model_dump(include={"category", "service", "root_cause", "fix"})


class Labels(BaseModel):
    category: Category | None
    service: str | None


class Judgment(BaseModel):
    agree: bool
    reason: str = Field(min_length=1)
