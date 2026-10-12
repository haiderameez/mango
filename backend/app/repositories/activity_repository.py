from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.activity import Activity, ActivityType


class ActivityRepository:
    def __init__(self, db: Session):
        self.db = db

    def record(
        self,
        incident_id: int,
        activity_type: ActivityType,
        user_id: int | None = None,
        detail: str | None = None,
        commit: bool = False,
    ) -> Activity:
        """Stage an activity row. Left uncommitted by default so callers can record the
        activity and the domain change it describes in a single transaction."""
        activity = Activity(
            incident_id=incident_id,
            activity_type=activity_type,
            user_id=user_id,
            detail=detail,
        )
        self.db.add(activity)

        if commit:
            self.db.commit()
            self.db.refresh(activity)

        return activity

    def get_by_incident(self, incident_id: int) -> list[Activity]:
        statement = (
            select(Activity)
            .where(Activity.incident_id == incident_id)
            .order_by(Activity.created_at, Activity.id)
        )
        return list(self.db.execute(statement).scalars().all())
