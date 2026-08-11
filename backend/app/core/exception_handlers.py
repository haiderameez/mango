from fastapi import Request
from fastapi.responses import JSONResponse

from app.core.exceptions import (IncidentAssignmentError, 
                                 IncidentNotFoundError,
                                 UserNotFoundError,
                                 IncidentStatusUpdateError,
                                 CommentNotFoundError,
                                 CommentNotAllowedError)

async def incident_not_found_handler(request: Request, exc: IncidentNotFoundError):
    return JSONResponse(status_code=404, content={"detail": str(exc)})

async def user_not_found_handler(request: Request, exc: UserNotFoundError):
    return JSONResponse(status_code=404, content={"detail": str(exc)})

async def incident_assignment_handler(request: Request, exc: IncidentAssignmentError):
    return JSONResponse(status_code=403, content={"detail": str(exc)})

async def incident_status_update_handler(request: Request, exc: IncidentStatusUpdateError):
    return JSONResponse(status_code=403, content={"detail": str(exc)})

async def comment_not_found_handler(request: Request, exc: CommentNotFoundError):
    return JSONResponse(status_code=404, content={"detail": str(exc)})

async def comment_not_allowed_handler(request: Request, exc: CommentNotAllowedError):
    return JSONResponse(status_code=403, content={"detail": str(exc)})