from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.dependencies import require_admin
from app.database.session import get_db
from app.models.user import User
from app.schemas.escalation import (
    EscalationPolicyCreate,
    EscalationPolicyResponse,
    EscalationPolicyUpdate,
)
from app.services.escalation_service import EscalationService

router = APIRouter(prefix="/escalation-policies", tags=["escalations"])


@router.get("", response_model=list[EscalationPolicyResponse])
def list_policies(
    _admin: User = Depends(require_admin), db: Session = Depends(get_db)
):
    return EscalationService(db).list_policies()


@router.post("", response_model=EscalationPolicyResponse, status_code=status.HTTP_201_CREATED)
def create_policy(
    data: EscalationPolicyCreate,
    _admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    try:
        return EscalationService(db).create_policy(data)
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error


@router.patch("/{policy_id}", response_model=EscalationPolicyResponse)
def update_policy(
    policy_id: int,
    data: EscalationPolicyUpdate,
    _admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    try:
        return EscalationService(db).update_policy(policy_id, data)
    except LookupError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
