import json

import main
from fastapi.testclient import TestClient


def test_checkout_failure_is_recorded_and_sent_to_mango(monkeypatch, tmp_path):
    log_path = tmp_path / "night-window.jsonl"
    monkeypatch.setattr(main, "LOG_PATH", log_path)
    sent = []
    client = TestClient(main.create_app(mango_sender=sent.append))

    response = client.post(
        "/api/orders",
        json={"product": "night-blend", "quantity": 2, "simulate_failure": True},
    )

    event = json.loads(log_path.read_text(encoding="utf-8"))
    assert response.status_code == 503
    assert response.headers["x-request-id"] == event["request_id"]
    assert event["service"] == "night-window-coffee"
    assert event["level"] == "ERROR"
    assert "payment gateway unavailable" in event["message"]
    assert sent == [event]


def test_successful_checkout_returns_an_order_and_records_info(monkeypatch, tmp_path):
    log_path = tmp_path / "night-window.jsonl"
    monkeypatch.setattr(main, "LOG_PATH", log_path)
    sent = []
    client = TestClient(main.create_app(mango_sender=sent.append))

    response = client.post("/api/orders", json={"product": "early-light", "quantity": 1})

    assert response.status_code == 200
    assert response.json()["status"] == "accepted"
    assert json.loads(log_path.read_text(encoding="utf-8"))["level"] == "INFO"
    assert len(sent) == 1


def test_local_coffee_reference_assets_are_served(monkeypatch, tmp_path):
    monkeypatch.setattr(main, "LOG_PATH", tmp_path / "night-window.jsonl")
    client = TestClient(main.create_app(mango_sender=lambda event: None))

    response = client.get("/assets/coffee-roasting-machine-at-cucuta-colombia.jpg")

    assert response.status_code == 200
    assert response.headers["content-type"] == "image/jpeg"
