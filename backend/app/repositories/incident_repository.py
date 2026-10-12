from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.incident import Incident, StatusLevel
from app.schemas.incident import IncidentFilters


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

    def get_all(self, filters: IncidentFilters | None = None) -> list[Incident]:
        filters = filters or IncidentFilters()
        statement = select(Incident)

        if filters.status is not None:
            statement = statement.where(Incident.status == filters.status)

        if filters.severity is not None:
            statement = statement.where(Incident.severity == filters.severity)

        if filters.assigned_to is not None:
            statement = statement.where(Incident.assigned_to == filters.assigned_to)

        if filters.created_by is not None:
            statement = statement.where(Incident.created_by == filters.created_by)

        if filters.search:
            statement = statement.where(Incident.title.ilike(f"%{filters.search}%"))

        statement = statement.order_by(Incident.id.desc())
        statement = statement.limit(filters.limit).offset(filters.offset)

        return list(self.db.execute(statement).scalars().all())

    def assign(self, incident: Incident, assigned_to: int) -> Incident:
        incident.assigned_to = assigned_to
        self.db.commit()
        self.db.refresh(incident)
        return incident

    def update_status(self, incident: Incident, status: StatusLevel) -> Incident:
        incident.status = status
        self.db.commit()
        self.db.refresh(incident)
        return incident
