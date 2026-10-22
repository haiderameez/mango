from datetime import datetime

from sqlalchemy import delete, func, or_, select, update
from sqlalchemy.orm import Session

from app.models.incident import Incident, IncidentGroup, StatusLevel
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

    def get_open_by_fingerprint(self, fingerprint: str) -> Incident | None:
        statement = select(Incident).where(
            Incident.fingerprint == fingerprint,
            Incident.status.in_((StatusLevel.OPEN, StatusLevel.INVESTIGATING)),
        )
        return self.db.execute(statement).scalar_one_or_none()

    def increment_occurrence(self, incident_id: int, count: int, seen_at: datetime) -> Incident:
        latest = func.max if self.db.bind.dialect.name == "sqlite" else func.greatest
        self.db.execute(
            update(Incident)
            .where(Incident.id == incident_id)
            .values(
                occurrence_count=Incident.occurrence_count + count,
                last_seen_at=latest(Incident.last_seen_at, seen_at),
            )
        )
        self.db.commit()
        return self.get_by_id(incident_id)

    def get_related(
        self, incident: Incident, since: datetime
    ) -> list[Incident]:
        correlation = []
        if incident.request_id:
            correlation.append(Incident.request_id == incident.request_id)
        if incident.upstream_name:
            correlation.append(Incident.upstream_name == incident.upstream_name)
        if not correlation:
            return []
        statement = select(Incident).where(
            Incident.id != incident.id,
            Incident.service.is_not(None),
            Incident.service != incident.service,
            Incident.last_seen_at.between(since, incident.last_seen_at),
            Incident.status.in_((StatusLevel.OPEN, StatusLevel.INVESTIGATING)),
            or_(*correlation),
        )
        return list(self.db.execute(statement).scalars())

    def get_service_incidents_since(self, service: str, since: datetime) -> list[Incident]:
        statement = select(Incident).where(
            Incident.service == service, Incident.created_at >= since
        )
        return list(self.db.execute(statement).scalars())

    def get_service_incidents_by_request_tag(self, service: str, tag: str) -> list[Incident]:
        statement = select(Incident).where(
            Incident.service == service,
            Incident.request_id.like(f"%:{tag}"),
        )
        return list(self.db.execute(statement).scalars())

    def add_group(self, group: IncidentGroup) -> IncidentGroup:
        self.db.add(group)
        self.db.flush()
        return group

    def set_group(self, incident_ids: list[int], group_id: int) -> None:
        self.db.execute(
            update(Incident).where(Incident.id.in_(incident_ids)).values(group_id=group_id)
        )
        self.db.commit()

    def merge_groups(self, group_ids: set[int], target_group_id: int) -> None:
        if len(group_ids) < 2:
            return
        old_group_ids = group_ids - {target_group_id}
        self.db.execute(
            update(Incident)
            .where(Incident.group_id.in_(old_group_ids))
            .values(group_id=target_group_id)
        )
        self.db.execute(delete(IncidentGroup).where(IncidentGroup.id.in_(old_group_ids)))
        self.db.commit()

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

        statement = statement.order_by(Incident.created_at.desc(), Incident.id.desc())
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

    def acknowledge(self, incident: Incident, acknowledged_at: datetime) -> Incident:
        incident.acknowledged_at = acknowledged_at
        self.db.commit()
        self.db.refresh(incident)
        return incident

    def get_due_for_escalation(self, severity: str, cutoff: datetime) -> list[Incident]:
        statement = (
            select(Incident)
            .where(
                Incident.severity == severity,
                Incident.status == StatusLevel.OPEN,
                Incident.acknowledged_at.is_(None),
                Incident.escalated_at.is_(None),
                Incident.created_at <= cutoff,
            )
            .with_for_update(skip_locked=True)
        )
        return list(self.db.execute(statement).scalars())

    def escalate(self, incident: Incident, user_id: int, when: datetime) -> Incident:
        incident.assigned_to = user_id
        incident.escalated_at = when
        self.db.commit()
        self.db.refresh(incident)
        return incident
