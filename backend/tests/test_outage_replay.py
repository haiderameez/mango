import json
import secrets
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy import select

from app.models.incident import Incident, SeverityLevel, StatusLevel
from app.models.ingest import DetectionRule, LogRecord, ServiceIngestKey
from app.models.user import User
from app.repositories.incident_repository import IncidentRepository
from app.repositories.ingest_repository import IngestRepository
from app.services.ingest_service import IngestService

FIXTURE = Path(__file__).resolve().parents[2] / "load" / "outage.jsonl"


def test_replay_marker_counts_only_its_service_and_run(db):
    now = datetime.now(UTC)
    db.add_all([
        LogRecord(
            service="outage-test", level="INFO", message="first", context={},
            request_id="req-1:run-a", ts=now,
        ),
        LogRecord(
            service="outage-test", level="INFO", message="second", context={},
            request_id="req-2:run-b", ts=now,
        ),
        LogRecord(
            service="other", level="INFO", message="third", context={},
            request_id="req-3:run-a", ts=now,
        ),
    ])
    db.commit()

    assert IngestRepository(db).count_by_service_and_request_tag("outage-test", "run-a") == 1


def test_replay_result_selects_only_incidents_with_its_run_tag(db):
    actor = User(name="Replay", email="tagged-replay@example.com", password_hash="test")
    db.add(actor)
    db.commit()
    db.add_all([
        Incident(
            title="Current run", severity=SeverityLevel.HIGH, status=StatusLevel.OPEN,
            created_by=actor.id,
            service="outage-test", request_id="req-1:run-a", occurrence_count=10,
        ),
        Incident(
            title="Previous run", severity=SeverityLevel.HIGH, status=StatusLevel.OPEN,
            created_by=actor.id,
            service="outage-test", request_id="req-2:run-b", occurrence_count=20,
        ),
    ])
    db.commit()

    rows = IncidentRepository(db).get_service_incidents_by_request_tag("outage-test", "run-a")

    assert [row.occurrence_count for row in rows] == [10]


def test_ten_thousand_record_fixture_collapses_400_failures_into_six_incidents(
    db, monkeypatch
):
    actor = User(name="Replay", email="replay@example.com", password_hash="test")
    db.add(actor)
    db.commit()
    token = IngestService.create_key(db, "outage-test", actor.id)
    key = db.execute(select(ServiceIngestKey)).scalar_one()
    db.add(DetectionRule(service="*", level="ERROR", threshold=5, window_seconds=60))
    db.commit()
    monkeypatch.setattr("app.services.ingest_service.notify_incident_created", lambda _: None)
    service = IngestService(db)
    run_tag = secrets.token_hex(8)
    rows = [json.loads(line) for line in FIXTURE.read_text(encoding="utf-8").splitlines()]

    assert service.authenticate(token).id == key.id
    assert len(rows) == 10_000
    accepted = 0
    for offset in range(0, len(rows), 500):
        batch = rows[offset:offset + 500]
        for row in batch:
            if row["level"] == "ERROR":
                row["error_type"] = f"{row['error_type']}:{run_tag}"
        body = "\n".join(json.dumps(row) for row in batch).encode()
        accepted += service.process_batch(key.id, body)

    incidents = db.execute(select(Incident)).scalars().all()
    assert accepted == 10_000
    assert len(incidents) == 6
    assert sum(incident.occurrence_count for incident in incidents) == 400
