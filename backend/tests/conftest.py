import json
import os

os.environ.setdefault("DATABASE_URL", "sqlite://")
os.environ.setdefault("JWT_SECRET_KEY", "test-secret-key-long-enough-for-hs256-abcdef")
os.environ.setdefault("ANTHROPIC_API_KEY", "test-key-not-used")
os.environ.setdefault("GOOGLE_API_KEY", "test-key-not-used")
os.environ.setdefault("AWS_SNS_TOPIC_ARN", "")

from datetime import UTC, datetime, timedelta  # noqa: E402

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import create_engine, event  # noqa: E402
from sqlalchemy.pool import StaticPool  # noqa: E402

from app.ai import graph  # noqa: E402
from app.api import ingest, investigation  # noqa: E402
from app.core.config import settings  # noqa: E402
from app.database.base import Base  # noqa: E402
from app.database.session import get_db  # noqa: E402
from app.main import app  # noqa: E402
from app.models import *  # noqa: E402, F403  (registers every table on Base.metadata)
from app.models.ingest import LogRecord  # noqa: E402
from tests.fake_llm import FakeLLM  # noqa: E402


@pytest.fixture
def engine():
    """One in-memory SQLite database per test, shared across connections."""
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )

    @event.listens_for(engine, "connect")
    def enforce_foreign_keys(connection, _record):
        connection.execute("PRAGMA foreign_keys=ON")

    Base.metadata.create_all(engine)
    yield engine
    engine.dispose()


@pytest.fixture
def session_factory(engine):
    from sqlalchemy.orm import sessionmaker

    return sessionmaker(bind=engine, autocommit=False, autoflush=False)


@pytest.fixture
def db(session_factory):
    session = session_factory()
    yield session
    session.close()


@pytest.fixture(autouse=True)
def isolated_llm_budget(tmp_path, monkeypatch):
    """Never let a test spend the real daily budget, or see another test's spending."""
    monkeypatch.setattr(settings, "llm_quota_file", str(tmp_path / "llm_quota.json"))
    monkeypatch.setattr(settings, "llm_requests_per_day", 1000)


@pytest.fixture
def client(session_factory, monkeypatch):
    def override_get_db():
        session = session_factory()
        try:
            yield session
        finally:
            session.close()

    # The investigation worker opens its own session; point it at the test database too.
    monkeypatch.setattr(investigation, "SessionLocal", session_factory)
    monkeypatch.setattr(ingest, "SessionLocal", session_factory)

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as test_client:
        yield test_client

    # Drain before monkeypatch is undone, so no queued run touches the real database.
    investigation.investigation_queue.wait_idle(30)
    app.dependency_overrides.clear()


def start_investigation(client, incident_id, headers, timeout=30):
    """Queue an investigation and wait for the worker to finish it."""
    response = client.post(f"/incidents/{incident_id}/investigate", headers=headers)
    assert investigation.investigation_queue.wait_idle(timeout), "the worker never went idle"
    return response


def register(client, email="engineer@example.com", password="hunter2hunter2", name="Engineer"):
    response = client.post(
        "/auth/register", json={"name": name, "email": email, "password": password}
    )
    assert response.status_code == 201, response.text
    return response.json()


def auth_headers(client, email="engineer@example.com", password="hunter2hunter2", name="Engineer"):
    """Register (idempotently) and return a bearer header for that user."""
    client.post("/auth/register", json={"name": name, "email": email, "password": password})

    response = client.post("/auth/login", json={"email": email, "password": password})
    assert response.status_code == 200, response.text

    return {"Authorization": f"Bearer {response.json()['access_token']}"}


@pytest.fixture
def headers(client):
    return auth_headers(client)


@pytest.fixture
def other_headers(client):
    return auth_headers(client, email="other@example.com", name="Other")


@pytest.fixture
def incident(client, headers):
    response = client.post(
        "/incidents",
        json={"title": "Checkout returning 500s", "description": "db errors", "severity": "HIGH"},
        headers=headers,
    )
    assert response.status_code == 201, response.text
    return response.json()


@pytest.fixture
def fake_llm(monkeypatch):
    monkeypatch.setattr(graph, "get_llm", FakeLLM)
    return FakeLLM


@pytest.fixture
def log_file(tmp_path, monkeypatch, db):
    now = datetime.now(UTC)
    records = [
        {
            "timestamp": (now - timedelta(minutes=2)).isoformat(),
            "level": "ERROR",
            "service": "dummycommerce",
            "endpoint": "POST /orders",
            "request_id": "abc123",
            "error_type": "OperationalError",
            "message": "could not connect to server: Connection refused",
        },
        {
            "timestamp": (now - timedelta(minutes=1)).isoformat(),
            "level": "INFO",
            "service": "dummycommerce",
            "endpoint": "GET /products",
            "message": "Listed products",
        },
    ]

    path = tmp_path / "app.jsonl"
    path.write_text("\n".join(json.dumps(r) for r in records), encoding="utf-8")
    monkeypatch.setattr(settings, "dummycommerce_log_path", str(path))
    db.add_all([
        LogRecord(
            ts=datetime.fromisoformat(record["timestamp"]),
            service=record["service"],
            level=record["level"],
            message=record["message"],
            request_id=record.get("request_id"),
            context={"endpoint": record.get("endpoint"), "error_type": record.get("error_type")},
        )
        for record in records
    ])
    db.commit()

    return path
