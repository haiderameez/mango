import gzip
import hashlib
import json
from datetime import UTC, datetime

import pytest
from sqlalchemy import select

from app.models.activity import Activity
from app.models.incident import Incident
from app.models.ingest import DetectionRule, LogRecord, ServiceIngestKey
from app.models.user import User
from app.services.ingest_service import IngestPayloadError, IngestService, parse_jsonl


def payload(*records):
    return "\n".join(json.dumps(record) for record in records).encode()


def record(**overrides):
    return {
        "timestamp": datetime.now(UTC).isoformat(),
        "service": "checkout",
        "level": "ERROR",
        "message": "database connection refused",
        **overrides,
    }


def user(db):
    item = User(name="Engineer", email="ingest@example.com", password_hash="test")
    db.add(item)
    db.commit()
    return item


def create_ingest_key(db, service="checkout"):
    actor = user(db)
    token = IngestService.create_key(db, service, actor.id)
    stored = db.execute(select(ServiceIngestKey)).scalar_one()
    assert stored.key_hash == hashlib.sha256(token.encode()).hexdigest()
    assert token not in stored.key_hash
    return actor, token, stored


def test_jsonl_parser_accepts_gzip_and_scrubs_secrets():
    data = record(password="secret", api_key="credential", error_type="DatabaseError")

    parsed = parse_jsonl(gzip.compress(payload(data)), compressed=True)

    assert parsed[0]["context"] == {"error_type": "DatabaseError"}
    assert parsed[0]["ts"].tzinfo is not None


@pytest.mark.parametrize(
    "body",
    [b"not json", b"[]", payload({"service": "checkout"}), b"\xff"],
)
def test_jsonl_parser_rejects_malformed_rows(body):
    with pytest.raises(IngestPayloadError):
        parse_jsonl(body)


def test_jsonl_parser_rejects_more_than_500_records():
    body = payload(*(record() for _ in range(501)))

    with pytest.raises(IngestPayloadError, match="at most 500"):
        parse_jsonl(body)


def test_jsonl_parser_rejects_an_incomplete_gzip_stream():
    body = gzip.compress(payload(record()))[:-4]

    with pytest.raises(IngestPayloadError, match="incomplete"):
        parse_jsonl(body, compressed=True)


def test_ingest_key_authenticates_and_only_accepts_its_service(db):
    _, token, key = create_ingest_key(db)
    service = IngestService(db)

    assert service.authenticate(token).id == key.id
    assert service.authenticate("wrong-key") is None
    assert service.process_batch(key.id, payload(record(service="payments"))) == 0
    assert db.execute(select(LogRecord)).scalars().all() == []


def test_five_matching_errors_open_an_incident_and_keep_activity(db, monkeypatch):
    actor, _, key = create_ingest_key(db)
    db.add(DetectionRule(service="*", level="ERROR", threshold=5, window_seconds=60))
    db.commit()
    monkeypatch.setattr("app.services.ingest_service.notify_incident_created", lambda _: None)
    batch = payload(*(record() for _ in range(5)))

    count = IngestService(db).process_batch(key.id, batch)

    incidents = db.execute(select(Incident)).scalars().all()
    activities = db.execute(select(Activity)).scalars().all()
    assert count == 5
    assert len(incidents) == 1
    assert incidents[0].created_by == actor.id
    assert "5 matching" in incidents[0].description
    assert len(activities) == 1


def test_error_rate_rule_uses_percentage_threshold(db):
    actor, _, key = create_ingest_key(db)
    db.add(DetectionRule(
        service="*", level="*", threshold=50, window_seconds=300, pattern="error_rate"
    ))
    db.commit()
    now = datetime.now(UTC)
    db.add_all([
        LogRecord(service="checkout", level="ERROR", message="failure", context={}, ts=now),
        LogRecord(service="checkout", level="INFO", message="ok", context={}, ts=now),
    ])
    db.commit()

    IngestService(db)._detect(
        [LogRecord(service="checkout", level="INFO", message="batch", context={}, ts=now)],
        actor.id,
    )

    assert db.execute(select(Incident)).scalars().all() == []


def test_ingest_endpoint_authenticates_before_accepting_payload(client, db):
    _, token, _ = create_ingest_key(db)

    unauthorized = client.post("/ingest/logs", content=payload(record()))
    accepted = client.post(
        "/ingest/logs", content=payload(record()), headers={"X-Ingest-Key": token}
    )

    assert unauthorized.status_code == 401
    assert accepted.status_code == 202
    assert len(db.execute(select(LogRecord)).scalars().all()) == 1


def test_ingest_endpoint_only_enqueues_the_batch(client, db, monkeypatch):
    _, token, key = create_ingest_key(db)
    queued = []
    monkeypatch.setattr(
        "app.api.ingest.enqueue_ingest_batch",
        lambda key_id, body, compressed: queued.append((key_id, body, compressed)),
    )
    body = payload(record())

    response = client.post(
        "/ingest/logs", content=body, headers={"X-Ingest-Key": token}
    )

    assert response.status_code == 202
    assert queued == [(key.id, body, False)]
    assert db.execute(select(LogRecord)).scalars().all() == []


def test_ingest_endpoint_accepts_gzip_payload(client, db):
    _, token, _ = create_ingest_key(db)
    response = client.post(
        "/ingest/logs",
        content=gzip.compress(payload(record())),
        headers={"X-Ingest-Key": token, "Content-Encoding": "gzip"},
    )

    assert response.status_code == 202
    assert len(db.execute(select(LogRecord)).scalars().all()) == 1


def test_ingest_endpoint_stops_reading_oversized_payload(client, db):
    _, token, _ = create_ingest_key(db)
    response = client.post(
        "/ingest/logs",
        content=b"x" * 1_000_001,
        headers={"X-Ingest-Key": token},
    )

    assert response.status_code == 413


def test_ingest_endpoint_rejects_unsupported_encoding(client, db):
    _, token, _ = create_ingest_key(db)
    response = client.post(
        "/ingest/logs",
        content=b"{}",
        headers={"X-Ingest-Key": token, "Content-Encoding": "br"},
    )

    assert response.status_code == 415
