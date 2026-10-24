from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.escalation import EscalationPolicy


class EscalationRepository:
    def __init__(self, db: Session):
        self.db = db

    def create(self, policy: EscalationPolicy) -> EscalationPolicy:
        self.db.add(policy)
        self.db.commit()
        self.db.refresh(policy)
        return policy

    def list_enabled(self) -> list[EscalationPolicy]:
        statement = (
            select(EscalationPolicy)
            .where(EscalationPolicy.enabled.is_(True))
            .order_by(EscalationPolicy.id)
        )
        return list(self.db.execute(statement).scalars())

    def get(self, policy_id: int) -> EscalationPolicy | None:
        return self.db.get(EscalationPolicy, policy_id)

    def save(self, policy: EscalationPolicy) -> EscalationPolicy:
        self.db.commit()
        self.db.refresh(policy)
        return policy

    def list_all(self) -> list[EscalationPolicy]:
        statement = select(EscalationPolicy).order_by(EscalationPolicy.id)
        return list(self.db.execute(statement).scalars())
