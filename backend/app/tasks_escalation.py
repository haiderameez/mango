from app.celery_app import celery_app
from app.database.session import SessionLocal
from app.services.escalation_service import EscalationService


@celery_app.task(name="app.tasks_escalation.check_due_escalations")
def check_due_escalations() -> int:
    with SessionLocal() as db:
        return EscalationService(db).run_due_escalations()
