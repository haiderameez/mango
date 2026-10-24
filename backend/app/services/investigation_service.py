import logging
from datetime import UTC, datetime

from app.ai.graph import NODE_ORDER, build_graph, take_thinking
from app.core.config import settings
from app.core.exceptions import (
    IncidentNotFoundError,
    InvestigationAlreadyRunningError,
    InvestigationNotFoundError,
)
from app.core.notifications import notify_investigation_completed
from app.models.activity import ActivityType
from app.models.incident import Incident
from app.models.workflow import AgentExecution, RunStatus, WorkflowRun
from app.observability import INVESTIGATIONS
from app.repositories.activity_repository import ActivityRepository
from app.repositories.incident_history_repository import IncidentHistoryRepository
from app.repositories.incident_repository import IncidentRepository
from app.repositories.ingest_repository import IngestRepository
from app.repositories.workflow_repository import WorkflowRepository
from app.schemas.workflow import (
    AgentExecutionResponse,
    InvestigationResponse,
    WorkflowRunResponse,
)
from app.services.incident_history import IncidentHistoryService

logger = logging.getLogger(__name__)

MAX_ERROR_LENGTH = 1000


def _incident_payload(incident: Incident) -> dict:
    """The incident as the workflow sees it: JSON-safe and only what the agents need."""
    return {
        "id": incident.id,
        "title": incident.title,
        "description": incident.description,
        "severity": incident.severity.value,
        "status": incident.status.value,
        "created_at": incident.created_at.isoformat(),
    }


class InvestigationService:
    def __init__(
        self,
        workflow_repository: WorkflowRepository,
        incident_repository: IncidentRepository,
        activity_repository: ActivityRepository,
    ):
        self.workflow_repository = workflow_repository
        self.incident_repository = incident_repository
        self.activity_repository = activity_repository
        self.ingest_repository = IngestRepository(incident_repository.db)
        self.history_service = IncidentHistoryService(
            IncidentHistoryRepository(incident_repository.db)
        )

    def start(
        self, incident_id: int, triggered_by: str, user_id: int | None = None
    ) -> WorkflowRunResponse:
        """Register a pending investigation. Does not execute it."""
        incident = self.incident_repository.get_by_id(incident_id)

        if incident is None:
            raise IncidentNotFoundError("Incident not found.")

        active_run = self.workflow_repository.get_active_run(incident_id)

        if active_run is not None:
            if self._is_stale(active_run):
                # The process that owned this run is gone, so it will never finish. Close it
                # out rather than blocking this incident's investigations forever.
                active_run.status = RunStatus.FAILED
                active_run.error = "Abandoned: the worker did not finish this run."
                active_run.finished_at = datetime.now(UTC)
                self.workflow_repository.save(active_run)
            else:
                raise InvestigationAlreadyRunningError(
                    "An investigation is already queued or running for this incident."
                )

        self.activity_repository.record(
            incident_id=incident_id,
            activity_type=ActivityType.INVESTIGATION_STARTED,
            user_id=user_id,
            detail=f"AI investigation triggered by {triggered_by}",
        )

        run = self.workflow_repository.create_run(
            WorkflowRun(
                incident_id=incident_id,
                triggered_by=triggered_by,
                status=RunStatus.PENDING,
            )
        )

        return WorkflowRunResponse.model_validate(run)

    def run(self, run_id: int, *, raise_on_failure: bool = False) -> None:
        """Execute the investigation graph, persisting progress as it goes.

        A background worker may request errors be re-raised so its task queue can retry.
        """
        run = self.workflow_repository.get_run(run_id)

        if run is None:
            raise InvestigationNotFoundError("Investigation not found.")

        if run.status == RunStatus.COMPLETED:
            return

        incident = self.incident_repository.get_by_id(run.incident_id)

        if incident is None:
            raise IncidentNotFoundError("Incident not found.")

        started_at = datetime.now(UTC)
        run.status = RunStatus.RUNNING
        run.error = None
        run.started_at = started_at
        self.workflow_repository.save(run)

        state: dict = {"incident": _incident_payload(incident)}
        completed_by_node = {
            execution.agent_name: execution
            for execution in self.workflow_repository.get_executions(run.id)
            if execution.status == RunStatus.COMPLETED
        }
        completed_nodes = 0
        for node_name in NODE_ORDER:
            execution = completed_by_node.get(node_name)
            if execution is None:
                break
            output = execution.output or {}
            if node_name == "report":
                state["report"] = output.get("report")
            else:
                state.update({key: value for key, value in output.items() if key != "thinking"})
            completed_nodes += 1

        # Deliberately the local value: a refresh hands back whatever the database stores,
        # which is naive on SQLite and would not subtract against an aware timestamp.
        node_started_at = started_at
        failure: Exception | None = None

        try:
            logger.info(
                "Investigation %s: incident #%s, resuming at %s",
                run.id,
                incident.id,
                NODE_ORDER[completed_nodes] if completed_nodes < len(NODE_ORDER) else "completion",
            )

            graph = build_graph(
                start_at=(NODE_ORDER[completed_nodes]
                          if completed_nodes < len(NODE_ORDER) else None),
                evidence_repository=self.ingest_repository,
                history_service=self.history_service,
            )
            updates = graph.stream(state, stream_mode="updates") if completed_nodes < len(
                NODE_ORDER
            ) else ()
            for update in updates:
                for node_name, delta in update.items():
                    finished_at = datetime.now(UTC)
                    state.update(delta)
                    completed_nodes += 1

                    output = self._execution_output(delta)
                    thinking = take_thinking()

                    if thinking:
                        output = {**output, "thinking": thinking}

                    logger.info(
                        "Investigation %s: %-18s done in %4.1fs - %s",
                        run.id,
                        node_name,
                        (finished_at - node_started_at).total_seconds(),
                        self._progress_summary(node_name, delta),
                    )

                    self.workflow_repository.add_execution(
                        AgentExecution(
                            workflow_run_id=run.id,
                            agent_name=node_name,
                            status=RunStatus.COMPLETED,
                            started_at=node_started_at,
                            finished_at=finished_at,
                            output=output,
                        )
                    )
                    node_started_at = finished_at

            run.report = state.get("report")
            run.status = RunStatus.COMPLETED
            run.finished_at = datetime.now(UTC)

            self.activity_repository.record(
                incident_id=run.incident_id,
                activity_type=ActivityType.INVESTIGATION_COMPLETED,
                detail=f"AI investigation #{run.id} completed",
            )

        except Exception as error:  # noqa: BLE001 - any node failure must land in the record
            failure = error
            logger.exception("Investigation %s failed", run.id)

            message = str(error)[:MAX_ERROR_LENGTH] or error.__class__.__name__

            # The graph is linear, so the node that failed is the one after the last that
            # reported an update.
            failed_node = (
                NODE_ORDER[completed_nodes] if completed_nodes < len(NODE_ORDER) else "unknown"
            )

            self.workflow_repository.add_execution(
                AgentExecution(
                    workflow_run_id=run.id,
                    agent_name=failed_node,
                    status=RunStatus.FAILED,
                    started_at=node_started_at,
                    finished_at=datetime.now(UTC),
                    error=message,
                )
            )

            run.status = RunStatus.FAILED
            run.error = message
            run.finished_at = datetime.now(UTC)

            self.activity_repository.record(
                incident_id=run.incident_id,
                activity_type=ActivityType.INVESTIGATION_FAILED,
                detail=f"AI investigation #{run.id} failed",
            )

        self.workflow_repository.save(run)
        INVESTIGATIONS.labels(run.status.value).observe(
            (datetime.now(UTC) - started_at).total_seconds()
        )
        if failure is not None and raise_on_failure:
            raise failure
        if failure is None and run.status == RunStatus.COMPLETED:
            notify_investigation_completed(incident, run.report)

    def get(self, run_id: int) -> InvestigationResponse:
        run = self.workflow_repository.get_run(run_id)

        if run is None:
            raise InvestigationNotFoundError("Investigation not found.")

        return self._to_response(run)

    def get_latest_for_incident(self, incident_id: int) -> InvestigationResponse:
        if self.incident_repository.get_by_id(incident_id) is None:
            raise IncidentNotFoundError("Incident not found.")

        runs = self.workflow_repository.get_by_incident(incident_id)

        if not runs:
            raise InvestigationNotFoundError("No investigation has been run for this incident.")

        return self._to_response(runs[0])

    def list_for_incident(self, incident_id: int) -> list[WorkflowRunResponse]:
        if self.incident_repository.get_by_id(incident_id) is None:
            raise IncidentNotFoundError("Incident not found.")

        return [
            WorkflowRunResponse.model_validate(run)
            for run in self.workflow_repository.get_by_incident(incident_id)
        ]

    def _to_response(self, run: WorkflowRun) -> InvestigationResponse:
        executions = self.workflow_repository.get_executions(run.id)

        return InvestigationResponse(
            **WorkflowRunResponse.model_validate(run).model_dump(),
            report=run.report,
            executions=[AgentExecutionResponse.model_validate(e) for e in executions],
        )

    @staticmethod
    def _progress_summary(node_name: str, delta: dict) -> str:
        """One readable line per agent, so an operator can follow a run in the log."""
        if "plan" in delta:
            steps = delta["plan"].get("steps", [])
            keyword = delta["plan"].get("log_keyword")
            return f"{len(steps)} step(s), log keyword {keyword!r}"

        if "evidence" in delta:
            return f"{len(delta['evidence'])} log record(s) collected"

        if "history" in delta:
            return f"{len(delta['history'])} similar resolved incident(s) found"

        if "root_cause" in delta:
            cause = delta["root_cause"].get("likely_cause", "")
            return f"[{delta['root_cause'].get('confidence')}] {cause[:90]}"

        if "recommendations" in delta:
            return f"{len(delta['recommendations'].get('actions', []))} action(s) recommended"

        if "report" in delta:
            return f"report assembled, {len(delta['report'] or '')} characters"

        return ""

    @staticmethod
    def _is_stale(run: WorkflowRun) -> bool:
        started = run.started_at or run.created_at

        if started.tzinfo is None:
            started = started.replace(tzinfo=UTC)

        age_minutes = (datetime.now(UTC) - started).total_seconds() / 60

        return age_minutes > settings.stale_run_minutes

    @staticmethod
    def _execution_output(delta: dict) -> dict:
        """What a node produced. The full report lives on the run, not duplicated here."""
        if "report" in delta:
            return {
                "report_characters": len(delta["report"] or ""),
                "report": delta["report"],
            }

        return delta
