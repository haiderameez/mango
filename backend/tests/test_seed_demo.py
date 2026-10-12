"""The demo seed has to produce a register a reviewer can actually read."""
import json
from datetime import UTC, datetime

import pytest

from app.models.activity import Activity
from app.models.comment import Comment
from app.models.incident import Incident, StatusLevel
from app.models.user import User
from app.models.workflow import AgentExecution, RunStatus, WorkflowRun
from scripts import seed_demo

STUB = [
    {
        "fault": fault,
        "triggered_by": "dummycommerce",
        "description": f"POST /orders failed ({fault})",
        "report": "## Probable cause\n\nAn upstream dependency.",
        "executions": [
            {
                "agent_name": "planner",
                "status": "COMPLETED",
                "started_at": "2026-10-12T10:00:00+00:00",
                "finished_at": "2026-10-12T10:00:04+00:00",
                "output": {"steps": ["search the logs"], "thinking": "Looking for a pattern."},
                "error": None,
            },
            {
                "agent_name": "report",
                "status": "COMPLETED",
                "started_at": "2026-10-12T10:00:04+00:00",
                "finished_at": "2026-10-12T10:00:05+00:00",
                "output": {"confidence": "medium"},
                "error": None,
            },
        ],
    }
    for fault in ("dependency_down", "db_connection")
]


@pytest.fixture
def seeded(db, tmp_path, monkeypatch):
    fixtures = tmp_path / "demo_fixtures.json"
    fixtures.write_text(json.dumps(STUB), encoding="utf-8")
    monkeypatch.setattr(seed_demo, "FIXTURES", fixtures)

    seed_demo.seed(db, reset=False)
    return db


def test_it_seeds_a_readable_register(seeded):
    incidents = seeded.query(Incident).all()

    assert len(incidents) == len(seed_demo.INCIDENTS)
    # A reviewer should see the whole severity range and more than one status at a glance.
    assert len({i.severity for i in incidents}) == 4
    assert len({i.status for i in incidents}) == 3
    assert all(i.description for i in incidents)


def test_the_demo_user_can_sign_in(seeded, client):
    response = client.post(
        "/auth/login",
        json={"email": seed_demo.USERS[0][1], "password": seed_demo.DEMO_PASSWORD},
    )

    assert response.status_code == 200, response.text


def test_the_investigations_are_complete_and_carry_their_executions(seeded):
    runs = seeded.query(WorkflowRun).all()

    assert len(runs) == 2
    for run in runs:
        assert run.status is RunStatus.COMPLETED
        assert run.report
        executions = (
            seeded.query(AgentExecution).filter(AgentExecution.workflow_run_id == run.id).all()
        )
        assert [e.agent_name for e in executions] == ["planner", "report"]
        assert all(e.finished_at > e.started_at for e in executions)


def test_nothing_is_dated_in_the_future(seeded):
    """Timestamps are rebased onto now, so an off-by-one would show tomorrow's incidents."""
    now = datetime.now(UTC)

    for row in seeded.query(Incident).all() + seeded.query(Activity).all():
        assert row.created_at.replace(tzinfo=UTC) <= now


def test_every_incident_has_a_timeline(seeded):
    for incident in seeded.query(Incident).all():
        activity = seeded.query(Activity).filter(Activity.incident_id == incident.id).all()
        assert activity, f"{incident.title} has no activity"

        if incident.status is not StatusLevel.OPEN:
            assert any(a.detail and "Status changed" in a.detail for a in activity)


def test_the_comments_belong_to_seeded_users(seeded):
    emails = {email for _, email in seed_demo.USERS}
    comments = seeded.query(Comment).all()

    assert comments
    for comment in comments:
        author = seeded.query(User).filter(User.id == comment.user_id).one()
        assert author.email in emails


def test_seeding_twice_is_refused_without_reset(seeded, tmp_path, monkeypatch):
    with pytest.raises(SystemExit, match="--reset"):
        seed_demo.seed(seeded, reset=False)


def test_the_shipped_fixtures_are_complete_investigations():
    """Guards the committed capture: a truncated fixture would seed an empty demo."""
    fixtures = json.loads(seed_demo.FIXTURES.read_text(encoding="utf-8"))

    faults = {f["fault"] for f in fixtures}
    assert {"dependency_down", "db_connection"} <= faults

    for fixture in fixtures:
        assert fixture["status"] == "COMPLETED"
        assert len(fixture["report"]) > 500
        assert [e["agent_name"] for e in fixture["executions"]] == [
            "planner",
            "evidence_collector",
            "root_cause",
            "fix_recommendation",
            "report",
        ]
