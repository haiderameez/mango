"""Self-check for DummyCommerce: pytest test_main.py (from this directory)."""
import json

import pytest
from fastapi.testclient import TestClient

import main


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(main, "LOG_PATH", tmp_path / "app.jsonl")
    monkeypatch.setattr(main, "armed_fault", None)
    monkeypatch.setattr(main, "MANGO_EMAIL", "")
    monkeypatch.setattr(main, "MANGO_PASSWORD", "")
    return TestClient(main.app)


def log_records():
    return [json.loads(line) for line in main.LOG_PATH.read_text(encoding="utf-8").splitlines()]


def test_orders_succeed_when_no_fault_is_armed(client):
    response = client.post("/orders", json={"product_id": 1, "quantity": 2})

    assert response.status_code == 201
    assert response.json()["total"] == 48.0
    assert log_records()[-1]["level"] == "INFO"


def test_unknown_product_is_a_404(client):
    assert client.post("/orders", json={"product_id": 99}).status_code == 404


def test_unknown_fault_is_rejected(client):
    assert client.post("/faults/nonsense").status_code == 404


def test_armed_db_fault_fails_the_order_and_logs_evidence(client):
    client.post("/faults/db_connection")

    response = client.post("/orders", json={"product_id": 1})

    assert response.status_code == 500

    failure = [r for r in log_records() if r.get("fault") == "db_connection"][-1]
    assert failure["endpoint"] == "POST /orders"
    assert failure["error_type"] == "OperationalError"
    assert "Connection refused" in failure["message"]
    assert failure["request_id"]


def test_a_failure_leaves_a_sequence_of_evidence_not_one_line(client):
    """An investigation can only be as good as the trail the application leaves."""
    client.post("/faults/db_connection")
    client.post("/orders", json={"product_id": 1})

    events = [r for r in log_records() if r.get("fault") == "db_connection"]
    messages = " ".join(r["message"] for r in events)

    assert len(events) >= 5
    assert len({r["request_id"] for r in events}) == 1, "one failed request, one correlation id"
    assert "pool" in messages and "retry" in messages and "Connection refused" in messages
    assert {r["level"] for r in events} == {"WARNING", "ERROR"}


def test_diagnostic_fields_are_logged_alongside_the_message(client):
    client.post("/faults/dependency_down")
    client.post("/orders", json={"product_id": 1})

    events = [r for r in log_records() if r.get("fault") == "dependency_down"]

    assert any(r.get("upstream_status") == 503 for r in events)
    assert any(r.get("circuit_state") == "OPEN" for r in events)


def test_clearing_the_fault_restores_the_endpoint(client):
    client.post("/faults/db_connection")
    client.delete("/faults")

    assert client.post("/orders", json={"product_id": 1}).status_code == 201


def test_degraded_fault_logs_a_warning_without_failing(client):
    client.post("/faults/slow")

    response = client.post("/orders", json={"product_id": 1})

    assert response.status_code == 201
    assert any(r["level"] == "WARNING" and r.get("fault") == "slow" for r in log_records())


def test_missing_mango_credentials_do_not_break_the_app(client):
    client.post("/faults/dependency_down")

    assert client.post("/orders", json={"product_id": 1}).status_code == 502
    assert any("credentials not configured" in r["message"] for r in log_records())


@pytest.mark.parametrize("fault", [
    "memory_pressure", "disk_full", "missing_field", "invalid_credentials",
    "invalid_endpoint", "lock_contention",
])
def test_benchmark_faults_emit_their_diagnostic_sequence(client, fault):
    assert client.post(f"/faults/{fault}").status_code == 200
    response = client.post("/orders", json={"product_id": 1})
    assert response.status_code == main.FAULTS[fault]["status"]
    events = [r for r in log_records() if r.get("fault") == fault]
    assert [r["message"] for r in events] == [e[1] for e in main.FAULTS[fault]["events"]]
    assert len({r["request_id"] for r in events}) == 1
