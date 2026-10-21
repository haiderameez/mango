from datetime import UTC, datetime, timedelta

from app.models.activity import Activity, ActivityType
from app.models.escalation import EscalationPolicy
from app.models.incident import Incident, SeverityLevel
from app.models.user import User
from app.repositories.user_repository import UserRepository
from app.services.escalation_service import EscalationService


def _user(db, email: str, role: str = "responder") -> User:
    user = User(name=email.split("@")[0], email=email, password_hash="test", role=role)
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def test_viewers_can_read_but_cannot_create_incidents(client, incident, db, headers):
    user = UserRepository(db).get_by_email("engineer@example.com")
    UserRepository(db).update_role(user, "viewer")
    viewer_headers = headers

    assert client.get("/incidents", headers=viewer_headers).status_code == 200
    denied = client.post(
        "/incidents",
        json={"title": "Blocked", "severity": "LOW"},
        headers=viewer_headers,
    )
    assert denied.status_code == 403


def test_admin_can_assign_an_incident_created_by_another_user(client, incident, db, headers):
    admin = UserRepository(db).get_by_email("engineer@example.com")
    UserRepository(db).update_role(admin, "admin")
    target = _user(db, "target@example.com")

    response = client.patch(
        f"/incidents/{incident['id']}/assign",
        json={"assigned_to": target.id},
        headers=headers,
    )

    assert response.status_code == 200
    assert response.json()["assigned_to"] == target.id


def test_admin_can_change_a_users_role(client, db, headers):
    admin = UserRepository(db).get_by_email("engineer@example.com")
    UserRepository(db).update_role(admin, "admin")
    target = _user(db, "target@example.com")

    response = client.patch(
        f"/auth/users/{target.id}/role", json={"role": "viewer"}, headers=headers
    )

    assert response.status_code == 200
    assert response.json()["role"] == "viewer"


def test_the_last_admin_cannot_demote_themselves(client, db, headers):
    admin = UserRepository(db).get_by_email("engineer@example.com")
    UserRepository(db).update_role(admin, "admin")

    response = client.patch(
        f"/auth/users/{admin.id}/role", json={"role": "viewer"}, headers=headers
    )

    assert response.status_code == 409


def test_due_unacknowledged_critical_incident_is_escalated(db):
    owner = _user(db, "owner@example.com")
    next_user = _user(db, "oncall@example.com")
    incident = Incident(
        title="Database unavailable",
        description="Connection refused",
        severity=SeverityLevel.CRITICAL,
        created_by=owner.id,
        created_at=datetime.now(UTC) - timedelta(minutes=11),
    )
    db.add(incident)
    db.add(EscalationPolicy(escalate_to_user_id=next_user.id, delay_minutes=10))
    db.commit()

    count = EscalationService(db).run_due_escalations()
    db.refresh(incident)

    assert count == 1
    assert incident.assigned_to == next_user.id
    assert incident.escalated_at is not None
    activity = db.query(Activity).filter_by(incident_id=incident.id).one()
    assert activity.activity_type == ActivityType.INCIDENT_ESCALATED


def test_acknowledged_incident_is_not_escalated(db):
    owner = _user(db, "owner@example.com")
    next_user = _user(db, "oncall@example.com")
    db.add(
        Incident(
            title="Acknowledged issue",
            description="Being handled",
            severity=SeverityLevel.CRITICAL,
            created_by=owner.id,
            acknowledged_at=datetime.now(UTC),
            created_at=datetime.now(UTC) - timedelta(minutes=11),
        )
    )
    db.add(EscalationPolicy(escalate_to_user_id=next_user.id, delay_minutes=10))
    db.commit()

    assert EscalationService(db).run_due_escalations() == 0
