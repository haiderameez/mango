import base64

from app.celery_app import celery_app
from app.core.exceptions import LlmQuotaExhaustedError, LlmRateLimitedError
from app.database.session import SessionLocal
from app.repositories.activity_repository import ActivityRepository
from app.repositories.incident_history_repository import IncidentHistoryRepository
from app.repositories.incident_repository import IncidentRepository
from app.repositories.workflow_repository import WorkflowRepository
from app.services.incident_history import IncidentHistoryService
from app.services.ingest_service import IngestService
from app.services.investigation_service import InvestigationService


def run_investigation_local(run_id: int) -> None:
    """Single-process test runner with the same database session boundary as Celery."""
    with SessionLocal() as db:
        service = InvestigationService(
            WorkflowRepository(db), IncidentRepository(db), ActivityRepository(db)
        )
        service.run(run_id)


@celery_app.task(
    name="app.tasks.run_investigation",
    acks_late=True,
    reject_on_worker_lost=True,
)
def run_investigation(run_id: int) -> None:
    with SessionLocal() as db:
        service = InvestigationService(
            WorkflowRepository(db), IncidentRepository(db), ActivityRepository(db)
        )
        service.run(run_id, raise_on_failure=True)


@celery_app.task(
    name="app.tasks.index_resolved_incident",
    autoretry_for=(LlmQuotaExhaustedError, LlmRateLimitedError),
    retry_backoff=3600,
    retry_backoff_max=21600,
    max_retries=8,
)
def index_resolved_incident(incident_id: int) -> bool:
    """Embed a resolved investigation asynchronously, retrying guarded provider deferrals."""
    with SessionLocal() as db:
        service = IncidentHistoryService(IncidentHistoryRepository(db))
        return service.index_resolved(incident_id)


def process_ingest_batch_local(key_id: int, payload: str, compressed: bool) -> int:
    """Synchronous fake for tests; production uses the Celery task below."""
    with SessionLocal() as db:
        return IngestService(db).process_batch(key_id, base64.b64decode(payload), compressed)


@celery_app.task(
    name="app.tasks.process_ingest_batch",
    acks_late=True,
    reject_on_worker_lost=True,
)
def process_ingest_batch(key_id: int, payload: str, compressed: bool) -> int:
    """Parse, persist, and detect in the dedicated ingestion queue worker."""
    return process_ingest_batch_local(key_id, payload, compressed)
