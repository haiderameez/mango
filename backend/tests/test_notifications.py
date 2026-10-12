import json

import pytest

from app.core import notifications
from app.core.config import settings
from app.models.incident import Incident, SeverityLevel, StatusLevel


class FakeSNS:
    def __init__(self):
        self.published = []

    def publish(self, **kwargs):
        self.published.append(kwargs)
        return {"MessageId": "fake"}


@pytest.fixture
def sns(monkeypatch):
    client = FakeSNS()
    monkeypatch.setattr(settings, "aws_sns_topic_arn", "arn:aws:sns:us-east-1:1:mango")
    monkeypatch.setattr("boto3.client", lambda *args, **kwargs: client)
    return client


def an_incident():
    return Incident(
        id=7,
        title="Checkout returning 500s",
        description="db errors",
        severity=SeverityLevel.CRITICAL,
        status=StatusLevel.OPEN,
        created_by=1,
        assigned_to=None,
    )


def test_publishes_incident_context(sns):
    notifications.notify_incident_created(an_incident())

    assert len(sns.published) == 1
    message = json.loads(sns.published[0]["Message"])
    assert message["incident_id"] == 7
    assert message["severity"] == "CRITICAL"
    assert "#7" in sns.published[0]["Subject"]


def test_subject_stays_within_the_sns_limit(sns):
    incident = an_incident()
    incident.title = "x" * 500

    notifications.notify_incident_created(incident)

    assert len(sns.published[0]["Subject"]) <= 100


def test_nothing_is_published_without_a_topic(monkeypatch):
    monkeypatch.setattr(settings, "aws_sns_topic_arn", None)
    monkeypatch.setattr(
        "boto3.client", lambda *a, **k: pytest.fail("SNS must not be called when unconfigured")
    )

    notifications.notify_incident_created(an_incident())


def test_a_publish_failure_is_swallowed(monkeypatch):
    monkeypatch.setattr(settings, "aws_sns_topic_arn", "arn:aws:sns:us-east-1:1:mango")
    monkeypatch.setattr("boto3.client", lambda *a, **k: (_ for _ in ()).throw(OSError("no net")))

    notifications.notify_incident_created(an_incident())


def test_incident_creation_survives_a_notification_outage(client, headers, monkeypatch):
    monkeypatch.setattr(settings, "aws_sns_topic_arn", "arn:aws:sns:us-east-1:1:mango")
    monkeypatch.setattr("boto3.client", lambda *a, **k: (_ for _ in ()).throw(OSError("no net")))

    response = client.post(
        "/incidents", json={"title": "still saved", "severity": "HIGH"}, headers=headers
    )

    assert response.status_code == 201
    assert client.get("/incidents", headers=headers).json()[0]["title"] == "still saved"


def test_creating_an_incident_publishes_one_notification(client, headers, sns):
    created = client.post(
        "/incidents", json={"title": "Checkout 500s", "severity": "HIGH"}, headers=headers
    ).json()

    assert len(sns.published) == 1
    assert json.loads(sns.published[0]["Message"])["incident_id"] == created["id"]


def test_status_changes_do_not_notify(client, headers, sns):
    created = client.post(
        "/incidents", json={"title": "Checkout 500s", "severity": "HIGH"}, headers=headers
    ).json()
    client.patch(
        f"/incidents/{created['id']}/status", json={"status": "INVESTIGATING"}, headers=headers
    )

    assert len(sns.published) == 1
