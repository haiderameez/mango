from app.repositories.incident_repository import IncidentRepository
from app.repositories.user_repository import UserRepository
from app.models.incident import Incident, StatusLevel
from app.schemas.incident import IncidentCreate, IncidentResponse
from app.core.exceptions import IncidentNotFoundError, IncidentAssignmentError, UserNotFoundError, IncidentStatusUpdateError

class IncidentService:
    def __init__(self, incident_repository: IncidentRepository, user_repository: UserRepository):
        self.incident_repository = incident_repository
        self.user_repository = user_repository
        
    def create(self, incident_data: IncidentCreate, created_by: int) -> IncidentResponse:
        new_incident = Incident(
            title=incident_data.title,
            description=incident_data.description,
            severity=incident_data.severity,
            created_by=created_by,
        )

        created_incident = self.incident_repository.create(new_incident)

        return IncidentResponse.model_validate(created_incident)

    def get_by_id(self, incident_id: int) -> IncidentResponse:
        incident = self.incident_repository.get_by_id(incident_id)

        if incident is None:
            raise IncidentNotFoundError(f"Incident not found.")

        return IncidentResponse.model_validate(incident)

    def get_all(self) -> list[IncidentResponse]:
        incidents = self.incident_repository.get_all()

        return [IncidentResponse.model_validate(incident) for incident in incidents]

    def assign(self, incident_id: int, assigned_to: int, current_user_id: int) -> IncidentResponse:
        incident = self.incident_repository.get_by_id(incident_id)

        if incident is None:
            raise IncidentNotFoundError("Incident not found.")

        user = self.user_repository.get_by_id(assigned_to)

        if user is None:
            raise UserNotFoundError("User not found.")

        if incident.status == StatusLevel.RESOLVED:
            raise IncidentAssignmentError("Resolved incident cannot be assigned.")

        if incident.created_by != current_user_id:
            raise IncidentAssignmentError("Only incident creator can assign.")

        updated_incident = self.incident_repository.assign(incident, assigned_to)

        return IncidentResponse.model_validate(updated_incident)

    def update_status(self, incident_id: int, new_status: StatusLevel, current_user_id: int) -> IncidentResponse:
        incident = self.incident_repository.get_by_id(incident_id)

        if incident is None:
            raise IncidentNotFoundError("Incident not found.")

        if not (incident.created_by == current_user_id or incident.assigned_to == current_user_id):
            raise IncidentStatusUpdateError("User not allowed to change status.")

        if incident.status == StatusLevel.OPEN:
            if new_status != StatusLevel.INVESTIGATING:
                raise IncidentStatusUpdateError("Invalid flow.")
        elif incident.status == StatusLevel.INVESTIGATING:
            if new_status != StatusLevel.RESOLVED:
                raise IncidentStatusUpdateError("Invalid flow.")
        elif incident.status == StatusLevel.RESOLVED:
            raise IncidentStatusUpdateError("Incident already resolved.")

        updated_incident = self.incident_repository.update_status(incident, new_status)

        return IncidentResponse.model_validate(updated_incident)