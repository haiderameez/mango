from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.ai import quota
from app.ai.graph import LLM_CALLS_PER_RUN
from app.core.config import settings
from app.core.dependencies import get_current_user
from app.database.session import SessionLocal, get_db
from app.models.user import User
from app.repositories.activity_repository import ActivityRepository
from app.repositories.incident_repository import IncidentRepository
from app.repositories.workflow_repository import WorkflowRepository
from app.schemas.workflow import InvestigationResponse, WorkflowRunResponse
from app.services.investigation_queue import InvestigationQueue
from app.services.investigation_service import InvestigationService

incident_investigation_router = APIRouter(prefix="/incidents", tags=["investigations"])
investigation_router = APIRouter(prefix="/investigations", tags=["investigations"])


def build_investigation_service(db: Session) -> InvestigationService:
    return InvestigationService(
        WorkflowRepository(db),
        IncidentRepository(db),
        ActivityRepository(db),
    )


def get_investigation_service(db: Session = Depends(get_db)) -> InvestigationService:
    return build_investigation_service(db)


def run_investigation(run_id: int) -> None:
    """Worker entry point. Owns its own session: the request's is already closed.

    ponytail: the queue lives in this process, so a restart loses what was still queued.
    Those runs stay PENDING in the database and can be re-triggered once they go stale.
    Move to a shared broker when investigations must survive a deploy.
    """
    db = SessionLocal()
    try:
        build_investigation_service(db).run(run_id)
    finally:
        db.close()


investigation_queue = InvestigationQueue(run_investigation)


@incident_investigation_router.post(
    "/{incident_id}/investigate",
    response_model=WorkflowRunResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
def start_investigation(
    incident_id: int,
    current_user: User = Depends(get_current_user),
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
