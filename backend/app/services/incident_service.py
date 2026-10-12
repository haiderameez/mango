from app.core.exceptions import (
    IncidentAssignmentError,
    IncidentNotFoundError,
    IncidentStatusUpdateError,
    UserNotFoundError,
)
from app.core.notifications import notify_incident_created
from app.models.activity import ActivityType
from app.models.incident import Incident, StatusLevel
from app.repositories.activity_repository import ActivityRepository
from app.repositories.incident_repository import IncidentRepository
from app.repositories.user_repository import UserRepository
from app.schemas.activity import ActivityResponse
from app.schemas.incident import IncidentCreate, IncidentFilters, IncidentResponse

# Allowed status transitions. Anything not listed here is rejected.
NEXT_STATUS = {
    StatusLevel.OPEN: {StatusLevel.INVESTIGATING},
    StatusLevel.INVESTIGATING: {StatusLevel.RESOLVED},
    StatusLevel.RESOLVED: set(),
}


class IncidentService:
    def __init__(
        self,
        incident_repository: IncidentRepository,
        user_repository: UserRepository,
        activity_repository: ActivityRepository,
    ):
        self.incident_repository = incident_repository
        self.user_repository = user_repository
        self.activity_repository = activity_repository

    def create(self, incident_data: IncidentCreate, created_by: int) -> IncidentResponse:
        new_incident = Incident(
            title=incident_data.title,
            description=incident_data.description,
            severity=incident_data.severity,
            created_by=created_by,
        )

        created_incident = self.incident_repository.create(new_incident)

        self.activity_repository.record(
            incident_id=created_incident.id,
            activity_type=ActivityType.INCIDENT_CREATED,
            user_id=created_by,
            detail=f"Incident created with severity {created_incident.severity.value}",
            commit=True,
        )

        # Best-effort and after the incident is committed: a notification outage must never
        # cost us the incident.
        # ponytail: published inline; move behind a worker if SNS latency shows up in p99.
        notify_incident_created(created_incident)

        return IncidentResponse.model_validate(created_incident)

    def get_by_id(self, incident_id: int) -> IncidentResponse:
        return IncidentResponse.model_validate(self._require_incident(incident_id))

    def get_all(self, filters: IncidentFilters | None = None) -> list[IncidentResponse]:
        incidents = self.incident_repository.get_all(filters)

        return [IncidentResponse.model_validate(incident) for incident in incidents]

    def assign(
        self, incident_id: int, assigned_to: int, current_user_id: int
    ) -> IncidentResponse:
        incident = self._require_incident(incident_id)

        user = self.user_repository.get_by_id(assigned_to)

        if user is None:
            raise UserNotFoundError("User not found.")

        if incident.status == StatusLevel.RESOLVED:
            raise IncidentAssignmentError("Resolved incident cannot be assigned.")

        if incident.created_by != current_user_id:
            raise IncidentAssignmentError("Only incident creator can assign.")

        # Staged before the update so the change and its history entry commit together.
        self.activity_repository.record(
            incident_id=incident.id,
            activity_type=(
                ActivityType.ASSIGNED if incident.assigned_to is None else ActivityType.REASSIGNED
            ),
            user_id=current_user_id,
            detail=f"Assigned to user {assigned_to}",
        )

        updated_incident = self.incident_repository.assign(incident, assigned_to)

        return IncidentResponse.model_validate(updated_incident)

    def update_status(
        self, incident_id: int, new_status: StatusLevel, current_user_id: int
    ) -> IncidentResponse:
        incident = self._require_incident(incident_id)

        if current_user_id not in (incident.created_by, incident.assigned_to):
            raise IncidentStatusUpdateError("User not allowed to change status.")

        if incident.status == StatusLevel.RESOLVED:
            raise IncidentStatusUpdateError("Incident already resolved.")

        if new_status not in NEXT_STATUS[incident.status]:
            raise IncidentStatusUpdateError(
                f"Invalid transition {incident.status.value} -> {new_status.value}."
            )

        previous_status = incident.status

        self.activity_repository.record(
            incident_id=incident.id,
            activity_type=ActivityType.STATUS_CHANGED,
            user_id=current_user_id,
            detail=f"{previous_status.value} -> {new_status.value}",
        )

        updated_incident = self.incident_repository.update_status(incident, new_status)

        return IncidentResponse.model_validate(updated_incident)

    def get_activity(self, incident_id: int) -> list[ActivityResponse]:
        self._require_incident(incident_id)

        return [
            ActivityResponse.model_validate(activity)
            for activity in self.activity_repository.get_by_incident(incident_id)
        ]

    def _require_incident(self, incident_id: int) -> Incident:
        incident = self.incident_repository.get_by_id(incident_id)

        if incident is None:
            raise IncidentNotFoundError("Incident not found.")

        return incident
