import asyncio
import json
import time

from fastapi import APIRouter, Depends, status
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.ai import quota
from app.ai.graph import LLM_CALLS_PER_RUN
from app.core.config import settings
from app.core.dependencies import get_current_user, require_responder
from app.database.session import SessionLocal, get_db
from app.models.user import User
from app.repositories.activity_repository import ActivityRepository
from app.repositories.incident_repository import IncidentRepository
from app.repositories.workflow_repository import WorkflowRepository
from app.schemas.workflow import InvestigationResponse, WorkflowRunResponse
from app.services.celery_queue import CeleryInvestigationQueue
from app.services.investigation_service import InvestigationService
from app.tasks import run_investigation

incident_investigation_router = APIRouter(prefix="/incidents", tags=["investigations"])
investigation_router = APIRouter(prefix="/investigations", tags=["investigations"])


def get_investigation_service(db: Session = Depends(get_db)) -> InvestigationService:
    return build_investigation_service(db)


@incident_investigation_router.get("/{incident_id}/investigation/stream")
def stream_investigation(
    incident_id: int,
    current_user: User = Depends(get_current_user),
    service: InvestigationService = Depends(get_investigation_service),
):
    """Stream finished agent steps and stored reasoning as server-sent events."""
    run_id = service.get_latest_for_incident(incident_id).id

    async def events():
        sent_ids = set()
        last_ping = time.monotonic()
        while True:
            with SessionLocal() as db:
                run = WorkflowRepository(db).get_run(run_id)
                executions = WorkflowRepository(db).get_executions(run_id)
                status_value = run.status.value
                error = run.error
                finished_at = run.finished_at.isoformat() if run.finished_at else None

            for execution in executions:
                if execution.id in sent_ids:
                    continue
                sent_ids.add(execution.id)
                event = {
                    "id": execution.id,
                    "agent_name": execution.agent_name,
                    "status": execution.status.value,
                    "output": execution.output,
                    "error": execution.error,
                    "started_at": (
                        execution.started_at.isoformat() if execution.started_at else None
                    ),
                    "finished_at": (
                        execution.finished_at.isoformat() if execution.finished_at else None
                    ),
                }
                yield f"event: agent\ndata: {json.dumps(event)}\n\n"

            if status_value in {"COMPLETED", "FAILED"}:
                done_event = {
                    "status": status_value, "error": error, "finished_at": finished_at
                }
                yield f"event: done\ndata: {json.dumps(done_event)}\n\n"
                return
            if time.monotonic() - last_ping >= 15:
                yield ": keep-alive\n\n"
                last_ping = time.monotonic()
            await asyncio.sleep(0.5)

    return StreamingResponse(
        events(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


def build_investigation_service(db: Session) -> InvestigationService:
    return InvestigationService(
        WorkflowRepository(db),
        IncidentRepository(db),
        ActivityRepository(db),
    )


investigation_queue = CeleryInvestigationQueue(run_investigation)


@incident_investigation_router.post(
    "/{incident_id}/investigate",
    response_model=WorkflowRunResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
def start_investigation(
    incident_id: int,
    current_user: User = Depends(require_responder),
    service: InvestigationService = Depends(get_investigation_service),
):
    """Queue an investigation. Returns immediately; one runs at a time."""
    run = service.start(
        incident_id,
        triggered_by=f"user:{current_user.id}",
        user_id=current_user.id,
    )

    investigation_queue.submit(run.id)

    return run


@incident_investigation_router.get(
    "/{incident_id}/investigation",
    response_model=InvestigationResponse,
    status_code=status.HTTP_200_OK,
)
def get_latest_investigation(
    incident_id: int,
    current_user: User = Depends(get_current_user),
    service: InvestigationService = Depends(get_investigation_service),
):
    return service.get_latest_for_incident(incident_id)


@incident_investigation_router.get(
    "/{incident_id}/investigations",
    response_model=list[WorkflowRunResponse],
    status_code=status.HTTP_200_OK,
)
def list_investigations(
    incident_id: int,
    current_user: User = Depends(get_current_user),
    service: InvestigationService = Depends(get_investigation_service),
):
    return service.list_for_incident(incident_id)


@investigation_router.get("/quota", status_code=status.HTTP_200_OK)
def get_quota(current_user: User = Depends(get_current_user)):
    """What is left of today's provider budget, and how much work is waiting for it."""
    return {
        "provider": settings.llm_provider,
        "requests_per_minute": settings.llm_requests_per_minute,
        "requests_per_day": settings.llm_requests_per_day,
        "requests_used_today": quota.used_today(),
        "requests_remaining_today": quota.remaining(),
        "investigations_affordable_today": quota.remaining() // LLM_CALLS_PER_RUN,
        "seconds_until_reset": round(quota.seconds_until_reset()),
        "queue_depth": investigation_queue.depth,
    }


@investigation_router.get(
    "/{run_id}",
    response_model=InvestigationResponse,
    status_code=status.HTTP_200_OK,
)
def get_investigation(
    run_id: int,
    current_user: User = Depends(get_current_user),
    service: InvestigationService = Depends(get_investigation_service),
):
    return service.get(run_id)
