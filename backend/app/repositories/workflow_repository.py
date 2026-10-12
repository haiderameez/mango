from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.workflow import AgentExecution, RunStatus, WorkflowRun


class WorkflowRepository:
    def __init__(self, db: Session):
        self.db = db

    def create_run(self, run: WorkflowRun) -> WorkflowRun:
        self.db.add(run)
        self.db.commit()
        self.db.refresh(run)
        return run

    def get_run(self, run_id: int) -> WorkflowRun | None:
        statement = select(WorkflowRun).where(WorkflowRun.id == run_id)
        return self.db.execute(statement).scalar_one_or_none()

    def get_by_incident(self, incident_id: int) -> list[WorkflowRun]:
        statement = (
            select(WorkflowRun)
            .where(WorkflowRun.incident_id == incident_id)
            .order_by(WorkflowRun.id.desc())
        )
        return list(self.db.execute(statement).scalars().all())

    def get_active_run(self, incident_id: int) -> WorkflowRun | None:
        """A pending or running investigation for this incident, if there is one."""
        statement = (
            select(WorkflowRun)
            .where(
                WorkflowRun.incident_id == incident_id,
                WorkflowRun.status.in_([RunStatus.PENDING, RunStatus.RUNNING]),
            )
            .order_by(WorkflowRun.id.desc())
        )
        return self.db.execute(statement).scalars().first()

    def save(self, run: WorkflowRun) -> WorkflowRun:
        self.db.commit()
        self.db.refresh(run)
        return run

    def add_execution(self, execution: AgentExecution) -> AgentExecution:
        self.db.add(execution)
        self.db.commit()
        self.db.refresh(execution)
        return execution

    def get_executions(self, run_id: int) -> list[AgentExecution]:
        statement = (
            select(AgentExecution)
            .where(AgentExecution.workflow_run_id == run_id)
            .order_by(AgentExecution.id)
        )
        return list(self.db.execute(statement).scalars().all())
