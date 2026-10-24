from datetime import UTC, datetime, timedelta

from sqlalchemy import select

from app.models.activity import Activity, ActivityType
from app.models.incident import Incident, StatusLevel
from app.models.ingest import DetectionRule, LogRecord
from app.models.user import User
from app.services.ingest_service import IngestService


def make_actor(db):
    actor = User(name="Engineer", email="dedup@example.com", password_hash="test")
    db.add(actor)
    db.commit()
    return actor


def make_record(service, message, *, request_id=None, upstream_name=None, when=None):
    return LogRecord(
        service=service,
        level="ERROR",
        message=message,
        request_id=request_id,
        context={"error_type": "OperationalError", "upstream_name": upstream_name},
        ts=when or datetime.now(UTC),
    )


def test_repeated_failures_bump_the_open_incident_count(db, monkeypatch):
    actor = make_actor(db)
    monkeypatch.setattr("app.services.ingest_service.notify_incident_created", lambda _: None)
    service = IngestService(db)
    rule = DetectionRule(service="*", level="ERROR", threshold=1, window_seconds=60)

    service._open_incident(
        rule, "checkout", [make_record("checkout", "DB 10.0.3.17:5432 timeout")], actor.id
    )
    service._open_incident(
        rule, "checkout", [make_record("checkout", "DB 10.0.4.2:6432 timeout")], actor.id
    )

    incidents = db.execute(select(Incident)).scalars().all()
    activities = db.execute(select(Activity)).scalars().all()
    assert len(incidents) == 1
    assert incidents[0].occurrence_count == 2
    assert [activity.activity_type for activity in activities] == [
        ActivityType.INCIDENT_CREATED,
        ActivityType.OCCURRENCE_DETECTED,
    ]


def test_rolling_detection_window_does_not_count_old_records_twice(db, monkeypatch):
    actor = make_actor(db)
    monkeypatch.setattr("app.services.ingest_service.notify_incident_created", lambda _: None)
    rule = DetectionRule(service="*", level="ERROR", threshold=2, window_seconds=60)
    db.add(rule)
    db.commit()
    service = IngestService(db)
    first_batch = [
        make_record("checkout", "database connection refused"),
        make_record("checkout", "database connection refused"),
    ]
    db.add_all(first_batch)
    db.commit()
    service._detect(first_batch, actor.id)
    new_record = make_record("checkout", "database connection refused")
    db.add(new_record)
    db.commit()

    service._detect([new_record], actor.id)

    incident = db.execute(select(Incident)).scalar_one()
    assert incident.occurrence_count == 3


def test_resolved_fingerprint_can_open_a_new_incident(db, monkeypatch):
    actor = make_actor(db)
    monkeypatch.setattr("app.services.ingest_service.notify_incident_created", lambda _: None)
    service = IngestService(db)
    rule = DetectionRule(service="*", level="ERROR", threshold=1, window_seconds=60)
    record = make_record("checkout", "database connection refused")
    service._open_incident(rule, "checkout", [record], actor.id)
    first = db.execute(select(Incident)).scalar_one()
    first.status = StatusLevel.RESOLVED
    db.commit()

    service._open_incident(rule, "checkout", [record], actor.id)

    assert len(db.execute(select(Incident)).scalars().all()) == 2


def test_cross_service_failures_share_a_correlation_group(db, monkeypatch):
    actor = make_actor(db)
    monkeypatch.setattr("app.services.ingest_service.notify_incident_created", lambda _: None)
    service = IngestService(db)
    rule = DetectionRule(service="*", level="ERROR", threshold=1, window_seconds=60)
    now = datetime.now(UTC)
    service._open_incident(
        rule,
        "checkout",
        [make_record("checkout", "request failed", request_id="req-42", when=now)],
        actor.id,
    )
    service._open_incident(
        rule,
        "payments",
        [make_record("payments", "upstream timeout", request_id="req-42", when=now)],
        actor.id,
    )

    incidents = db.execute(select(Incident).order_by(Incident.id)).scalars().all()
    assert len(incidents) == 2
    assert incidents[0].fingerprint != incidents[1].fingerprint
    assert incidents[0].group_id is not None
    assert incidents[0].group_id == incidents[1].group_id


def test_incidents_outside_the_correlation_window_stay_separate(db, monkeypatch):
    actor = make_actor(db)
    monkeypatch.setattr("app.services.ingest_service.notify_incident_created", lambda _: None)
    service = IngestService(db)
    rule = DetectionRule(service="*", level="ERROR", threshold=1, window_seconds=60)
    now = datetime.now(UTC)
    service._open_incident(
        rule,
        "checkout",
        [make_record("checkout", "request failed", request_id="req-42", when=now)],
        actor.id,
    )
    service._open_incident(
        rule,
        "payments",
        [make_record("payments", "upstream timeout", request_id="req-42",
                     when=now + timedelta(minutes=6))],
        actor.id,
    )

    incidents = db.execute(select(Incident).order_by(Incident.id)).scalars().all()
    assert incidents[0].group_id is None
    assert incidents[1].group_id is None
