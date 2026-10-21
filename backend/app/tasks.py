from app.celery_app import celery_app
from app.database.session import SessionLocal
from app.repositories.activity_repository import ActivityRepository
from app.repositories.incident_repository import IncidentRepository
from app.repositories.workflow_repository import WorkflowRepository
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
