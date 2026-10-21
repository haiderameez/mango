import json
import secrets
from pathlib import Path

from sqlalchemy import select

from app.models.incident import Incident
from app.models.ingest import DetectionRule, ServiceIngestKey
from app.models.user import User
from app.services.ingest_service import IngestService

FIXTURE = Path(__file__).resolve().parents[2] / "load" / "outage.jsonl"


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
