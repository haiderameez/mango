from datetime import UTC, datetime, timedelta

from sqlalchemy.orm import Session

from app.core.notifications import notify_escalation
from app.models.activity import ActivityType
from app.models.escalation import EscalationPolicy
from app.repositories.activity_repository import ActivityRepository
from app.repositories.escalation_repository import EscalationRepository
from app.repositories.incident_repository import IncidentRepository
from app.repositories.user_repository import UserRepository
from app.schemas.escalation import (
    EscalationPolicyCreate,
    EscalationPolicyResponse,
    EscalationPolicyUpdate,
)


class EscalationService:
    def __init__(self, db: Session):
        self.policies = EscalationRepository(db)
        self.incidents = IncidentRepository(db)
        self.users = UserRepository(db)
        self.activities = ActivityRepository(db)

    def create_policy(self, data: EscalationPolicyCreate) -> EscalationPolicyResponse:
        if self.users.get_by_id(data.escalate_to_user_id) is None:
            raise ValueError("Escalation target user does not exist.")
        policy = self.policies.create(EscalationPolicy(**data.model_dump()))
        return EscalationPolicyResponse.model_validate(policy)

    def list_policies(self) -> list[EscalationPolicyResponse]:
        return [EscalationPolicyResponse.model_validate(p) for p in self.policies.list_all()]

    def update_policy(
        self, policy_id: int, data: EscalationPolicyUpdate
    ) -> EscalationPolicyResponse:
        policy = self.policies.get(policy_id)
        if policy is None:
            raise LookupError("Escalation policy not found.")
        policy.enabled = data.enabled
        return EscalationPolicyResponse.model_validate(self.policies.save(policy))

    def run_due_escalations(self) -> int:
        now = datetime.now(UTC)
        escalated = 0
        for policy in self.policies.list_enabled():
            cutoff = now - timedelta(minutes=policy.delay_minutes)
            incidents = self.incidents.get_due_for_escalation(policy.severity, cutoff)
            target = self.users.get_by_id(policy.escalate_to_user_id)
            if target is None:
                continue
            for incident in incidents:
                self.activities.record(
                    incident.id,
                    ActivityType.INCIDENT_ESCALATED,
                    detail=f"Escalated to {target.name} after {policy.delay_minutes} minutes.",
                )
                self.incidents.escalate(incident, target.id, now)
                notify_escalation(incident, target.name)
                escalated += 1
        return escalated
