from datetime import datetime

from pydantic import BaseModel, ConfigDict

from app.models.workflow import RunStatus


class AgentExecutionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    agent_name: str
    status: RunStatus
    started_at: datetime | None
    finished_at: datetime | None
    output: dict | None
    error: str | None


class WorkflowRunResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    incident_id: int
    status: RunStatus
    triggered_by: str
    started_at: datetime | None
    finished_at: datetime | None
    error: str | None
    created_at: datetime


class InvestigationResponse(WorkflowRunResponse):
    """A workflow run plus everything it produced."""

    report: str | None
    executions: list[AgentExecutionResponse]
