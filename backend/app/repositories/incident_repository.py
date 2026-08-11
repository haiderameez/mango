from sqlalchemy.orm import Session
from sqlalchemy import select

from app.models.incident import Incident, StatusLevel

class IncidentRepository:
    def __init__(self, db: Session):
        self.db = db

    def create(self, incident: Incident) -> Incident:
        self.db.add(incident)
        self.db.commit()
        self.db.refresh(incident)
        return incident

    def get_by_id(self, incident_id: int) -> Incident | None:
        statement = select(Incident).where(Incident.id == incident_id)
        return self.db.execute(statement).scalar_one_or_none()

    def get_all(self) -> list[Incident]:
        statement = select(Incident)
        return self.db.execute(statement).scalars().all()

    def assign(self, incident: Incident, assigned_to: int) -> Incident:
        incident.assigned_to = assigned_to
        self.db.commit()
        self.db.refresh(incident)
        return incident

    def update_status(self, incident: Incident, status:StatusLevel) -> Incident:
        incident.status = status
        self.db.commit()
        self.db.refresh(incident)
        return incident