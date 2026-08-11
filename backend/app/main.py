from fastapi import FastAPI

from app.api.auth import router as auth_router
from app.api.incident import router as incident_router
from app.api.incident import comment_router 
from app.core.exception_handlers import (
    incident_assignment_handler,
    incident_not_found_handler,
    user_not_found_handler,
    incident_status_update_handler,
    comment_not_found_handler,
    comment_not_allowed_handler
)
from app.core.exceptions import (
    IncidentAssignmentError,
    UserNotFoundError,
    IncidentNotFoundError,
    IncidentStatusUpdateError,
    CommentNotFoundError,
    CommentNotAllowedError
)

app = FastAPI()

app.add_exception_handler(IncidentNotFoundError, incident_not_found_handler,)

app.add_exception_handler(UserNotFoundError, user_not_found_handler,)

app.add_exception_handler(IncidentAssignmentError, incident_assignment_handler,)

app.add_exception_handler(IncidentStatusUpdateError, incident_status_update_handler)

app.add_exception_handler(CommentNotFoundError, comment_not_found_handler)

app.add_exception_handler(CommentNotAllowedError, comment_not_allowed_handler)

app.include_router(auth_router)
app.include_router(incident_router)
app.include_router(comment_router)