from typing import Annotated

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session

from app.core.dependencies import get_current_user
from app.database.session import get_db
from app.models.user import User
from app.repositories.activity_repository import ActivityRepository
from app.repositories.comment_repository import CommentRepository
from app.repositories.incident_repository import IncidentRepository
from app.repositories.user_repository import UserRepository
from app.schemas.activity import ActivityResponse
from app.schemas.comment import CommentCreate, CommentResponse, CommentUpdate
from app.schemas.incident import (
    IncidentAssign,
    IncidentCreate,
    IncidentFilters,
    IncidentResponse,
    IncidentStatusUpdate,
)
from app.services.comment_service import CommentService
from app.services.incident_service import IncidentService

router = APIRouter(
    prefix="/incidents",
    tags=["incidents"],
)

comment_router = APIRouter(
    prefix="/comments",
    tags=["comments"],
)


def get_incident_service(db: Session = Depends(get_db)) -> IncidentService:
    return IncidentService(
        IncidentRepository(db),
        UserRepository(db),
        ActivityRepository(db),
    )


def get_comment_service(db: Session = Depends(get_db)) -> CommentService:
    return CommentService(
        CommentRepository(db),
        IncidentRepository(db),
        ActivityRepository(db),
    )


@router.post(
    "",
    response_model=IncidentResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_incident(
    incident_data: IncidentCreate,
    current_user: User = Depends(get_current_user),
    service: IncidentService = Depends(get_incident_service),
):
    return service.create(incident_data, created_by=current_user.id)


@router.get(
    "",
    response_model=list[IncidentResponse],
    status_code=status.HTTP_200_OK,
)
def get_incidents(
    filters: Annotated[IncidentFilters, Query()],
    current_user: User = Depends(get_current_user),
    service: IncidentService = Depends(get_incident_service),
):
    return service.get_all(filters)


@router.get(
    "/{incident_id}",
    response_model=IncidentResponse,
    status_code=status.HTTP_200_OK,
)
def get_incident(
    incident_id: int,
    current_user: User = Depends(get_current_user),
    service: IncidentService = Depends(get_incident_service),
):
    return service.get_by_id(incident_id)


@router.patch(
    "/{incident_id}/assign",
    response_model=IncidentResponse,
    status_code=status.HTTP_200_OK,
)
def assign_incident(
    incident_id: int,
    assignment_data: IncidentAssign,
    current_user: User = Depends(get_current_user),
    service: IncidentService = Depends(get_incident_service),
):
    return service.assign(
        incident_id=incident_id,
        assigned_to=assignment_data.assigned_to,
        current_user_id=current_user.id,
    )


@router.patch(
    "/{incident_id}/status",
    response_model=IncidentResponse,
    status_code=status.HTTP_200_OK,
)
def update_status(
    incident_id: int,
    status_data: IncidentStatusUpdate,
    current_user: User = Depends(get_current_user),
    service: IncidentService = Depends(get_incident_service),
):
    return service.update_status(
        incident_id=incident_id,
        new_status=status_data.status,
        current_user_id=current_user.id,
    )


@router.get(
    "/{incident_id}/activity",
    response_model=list[ActivityResponse],
    status_code=status.HTTP_200_OK,
)
def get_incident_activity(
    incident_id: int,
    current_user: User = Depends(get_current_user),
    service: IncidentService = Depends(get_incident_service),
):
    return service.get_activity(incident_id)


@router.post(
    "/{incident_id}/comments",
    response_model=CommentResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_comment(
    comment: CommentCreate,
    incident_id: int,
    current_user: User = Depends(get_current_user),
    service: CommentService = Depends(get_comment_service),
):
    return service.create(comment, incident_id=incident_id, current_user_id=current_user.id)


@router.get(
    "/{incident_id}/comments",
    response_model=list[CommentResponse],
    status_code=status.HTTP_200_OK,
)
def get_all_comments(
    incident_id: int,
    current_user: User = Depends(get_current_user),
    service: CommentService = Depends(get_comment_service),
):
    return service.get_all_comments(incident_id)


@comment_router.get(
    "/{comment_id}",
    response_model=CommentResponse,
    status_code=status.HTTP_200_OK,
)
def get_comment(
    comment_id: int,
    current_user: User = Depends(get_current_user),
    service: CommentService = Depends(get_comment_service),
):
    return service.get_comment(comment_id)


@comment_router.patch(
    "/{comment_id}",
    response_model=CommentResponse,
    status_code=status.HTTP_200_OK,
)
def update_comment(
    comment_id: int,
    comment: CommentUpdate,
    current_user: User = Depends(get_current_user),
    service: CommentService = Depends(get_comment_service),
):
    return service.update_comment(
        comment_id=comment_id,
        comment=comment,
        current_user_id=current_user.id,
    )


@comment_router.delete(
    "/{comment_id}",
    response_model=None,
    status_code=status.HTTP_204_NO_CONTENT,
)
def delete_comment(
    comment_id: int,
    current_user: User = Depends(get_current_user),
    service: CommentService = Depends(get_comment_service),
):
    return service.delete_comment(comment_id=comment_id, current_user_id=current_user.id)
