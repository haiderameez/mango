from datetime import UTC, datetime

from sqlalchemy import and_, func, select
from sqlalchemy.orm import Session, aliased

from app.models.incident import Incident, StatusLevel
from app.models.incident_embedding import IncidentEmbedding
from app.models.workflow import AgentExecution, RunStatus, WorkflowRun


class IncidentHistoryRepository:
    def __init__(self, db: Session):
        self.db = db

    def get_resolved_diagnosis(self, incident_id: int) -> dict | None:
        statement = (
            select(Incident, AgentExecution)
            .join(WorkflowRun, WorkflowRun.incident_id == Incident.id)
            .join(
                AgentExecution,
                (AgentExecution.workflow_run_id == WorkflowRun.id)
                & (AgentExecution.agent_name == "root_cause"),
            )
            .where(
                Incident.id == incident_id,
                Incident.status == StatusLevel.RESOLVED,
                WorkflowRun.status == RunStatus.COMPLETED,
                AgentExecution.status == RunStatus.COMPLETED,
            )
            .order_by(WorkflowRun.finished_at.desc(), WorkflowRun.id.desc())
            .limit(1)
        )
        row = self.db.execute(statement).first()
        if row is None:
            return None

        incident, execution = row
        recommendations = self._recommendations(execution.workflow_run_id)
        diagnosis = execution.output or {}
        return {
            "incident_id": incident.id,
            "title": incident.title,
            "description": incident.description or "",
            "likely_cause": diagnosis.get("likely_cause", ""),
            "fix": recommendations.get("actions", []),
            "resolved_at": incident.updated_at,
        }

    def get_unindexed_resolved_diagnoses(self, *, limit: int = 500) -> list[dict]:
        statement = (
            select(Incident.id)
            .join(WorkflowRun, WorkflowRun.incident_id == Incident.id)
            .join(AgentExecution, AgentExecution.workflow_run_id == WorkflowRun.id)
            .outerjoin(IncidentEmbedding, IncidentEmbedding.incident_id == Incident.id)
            .where(
                Incident.status == StatusLevel.RESOLVED,
                WorkflowRun.status == RunStatus.COMPLETED,
                AgentExecution.agent_name == "root_cause",
                AgentExecution.status == RunStatus.COMPLETED,
                IncidentEmbedding.incident_id.is_(None),
            )
            .distinct()
            .order_by(Incident.id)
            .limit(limit)
        )
        return [
            record
            for incident_id in self.db.execute(statement).scalars()
            if (record := self.get_resolved_diagnosis(incident_id)) is not None
        ]

    def has_embeddings(self) -> bool:
        return self.db.execute(select(IncidentEmbedding.incident_id).limit(1)).first() is not None

    def embedding_count(self) -> int:
        return self.db.execute(select(func.count()).select_from(IncidentEmbedding)).scalar_one()

    def _recommendations(self, run_id: int) -> dict:
        statement = select(AgentExecution.output).where(
            AgentExecution.workflow_run_id == run_id,
            AgentExecution.agent_name == "fix_recommendation",
            AgentExecution.status == RunStatus.COMPLETED,
        )
        return self.db.execute(statement).scalar_one_or_none() or {}

    def save_embedding(self, incident_id: int, embedding: list[float]) -> None:
        existing = self.db.get(IncidentEmbedding, incident_id)
        if existing is None:
            self.db.add(IncidentEmbedding(incident_id=incident_id, embedding=embedding))
        else:
            existing.embedding = embedding
            existing.created_at = datetime.now(UTC)
        self.db.commit()

    def save_embeddings(self, embeddings: dict[int, list[float]]) -> None:
        for incident_id, vector in embeddings.items():
            existing = self.db.get(IncidentEmbedding, incident_id)
            if existing is None:
                self.db.add(IncidentEmbedding(incident_id=incident_id, embedding=vector))
            else:
                existing.embedding = vector
                existing.created_at = datetime.now(UTC)
        self.db.commit()

    def search(self, embedding: list[float], *, limit: int, floor: float) -> list[dict]:
        distance = IncidentEmbedding.embedding.cosine_distance(embedding)
        latest_runs = (
            select(
                WorkflowRun.incident_id.label("incident_id"),
                func.max(WorkflowRun.id).label("run_id"),
            )
            .where(WorkflowRun.status == RunStatus.COMPLETED)
            .group_by(WorkflowRun.incident_id)
            .subquery()
        )
        root_cause_execution = aliased(AgentExecution)
        fix_execution = aliased(AgentExecution)
        statement = (
            select(
                Incident,
                root_cause_execution.output,
                fix_execution.output,
                distance.label("distance"),
            )
            .join(IncidentEmbedding, IncidentEmbedding.incident_id == Incident.id)
            .join(latest_runs, latest_runs.c.incident_id == Incident.id)
            .join(
                root_cause_execution,
                and_(
                    root_cause_execution.workflow_run_id == latest_runs.c.run_id,
                    root_cause_execution.agent_name == "root_cause",
                    root_cause_execution.status == RunStatus.COMPLETED,
                ),
            )
            .outerjoin(
                fix_execution,
                and_(
                    fix_execution.workflow_run_id == latest_runs.c.run_id,
                    fix_execution.agent_name == "fix_recommendation",
                    fix_execution.status == RunStatus.COMPLETED,
                ),
            )
            .where(Incident.status == StatusLevel.RESOLVED, distance <= 1 - floor)
            .order_by(distance)
            .limit(limit)
        )
        results = []
        for incident, diagnosis_output, fix_output, raw_distance in self.db.execute(statement):
            similarity = 1 - float(raw_distance)
            results.append(
                {
                    "incident_id": incident.id,
                    "title": incident.title,
                    "likely_cause": (diagnosis_output or {}).get("likely_cause", ""),
                    "fix": (fix_output or {}).get("actions", []),
                    "resolved_at": incident.updated_at,
                    "similarity": similarity,
                }
            )
        return results
