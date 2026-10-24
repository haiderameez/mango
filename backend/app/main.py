import logging

from fastapi import FastAPI

from app.api.auth import router as auth_router
from app.api.console import router as console_router
from app.api.escalation import router as escalation_router
from app.api.incident import comment_router
from app.api.incident import router as incident_router
from app.api.ingest import router as ingest_router
from app.api.investigation import incident_investigation_router, investigation_router
from app.core.config import settings
from app.core.exception_handlers import (
    comment_not_allowed_handler,
    comment_not_found_handler,
    incident_assignment_handler,
    incident_not_found_handler,
    incident_status_update_handler,
    investigation_already_running_handler,
    investigation_not_found_handler,
    user_not_found_handler,
)
from app.core.exceptions import (
    CommentNotAllowedError,
    CommentNotFoundError,
    IncidentAssignmentError,
    IncidentNotFoundError,
    IncidentStatusUpdateError,
    InvestigationAlreadyRunningError,
    InvestigationNotFoundError,
    UserNotFoundError,
)
from app.observability import MetricsMiddleware, configure_tracing, metrics_response

# Uvicorn only configures its own loggers, so the application's progress and the agents'
# reasoning would otherwise be invisible in the console.
logging.basicConfig(
    level=settings.log_level,
    format="%(asctime)s %(levelname)-7s %(name)s | %(message)s",
    datefmt="%H:%M:%S",
)

app = FastAPI(
    title="Mango",
    description="AI-assisted incident management and investigation.",
    version="1.0.0",
)
app.add_middleware(MetricsMiddleware)

app.add_exception_handler(IncidentNotFoundError, incident_not_found_handler)
app.add_exception_handler(UserNotFoundError, user_not_found_handler)
app.add_exception_handler(IncidentAssignmentError, incident_assignment_handler)
app.add_exception_handler(IncidentStatusUpdateError, incident_status_update_handler)
app.add_exception_handler(CommentNotFoundError, comment_not_found_handler)
app.add_exception_handler(CommentNotAllowedError, comment_not_allowed_handler)
app.add_exception_handler(InvestigationNotFoundError, investigation_not_found_handler)
app.add_exception_handler(InvestigationAlreadyRunningError, investigation_already_running_handler)

app.include_router(console_router)
app.include_router(auth_router)
app.include_router(incident_router)
app.include_router(comment_router)
app.include_router(incident_investigation_router)
app.include_router(investigation_router)
app.include_router(ingest_router)
app.include_router(escalation_router)


@app.get("/health", tags=["operations"])
def health():
    return {"status": "ok"}


@app.get("/metrics", include_in_schema=False)
def metrics():
    return metrics_response()


configure_tracing(app)
