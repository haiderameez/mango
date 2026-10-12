
import threading
import time

import pytest

from app.ai import graph
from app.ai.schemas import RootCause
from app.core.config import settings
from tests.conftest import start_investigation
from tests.fake_llm import FakeLLM


def test_start_investigation_runs_it_and_returns_a_report(
    client, incident, headers, fake_llm, log_file
):
    started = start_investigation(client, incident["id"], headers)

    assert started.status_code == 202
    assert started.json()["status"] == "PENDING"

    body = client.get(f"/incidents/{incident['id']}/investigation", headers=headers).json()

    assert body["status"] == "COMPLETED"
    assert body["error"] is None
    assert body["started_at"] and body["finished_at"]
    assert body["triggered_by"].startswith("user:")
    assert "orders-db is refusing connections" in body["report"]
    assert "Connection refused" in body["report"]
    assert "Confidence: medium" in body["report"]


def test_every_node_is_recorded_as_an_agent_execution(
    client, incident, headers, fake_llm, log_file
):
    start_investigation(client, incident["id"], headers)

    body = client.get(f"/incidents/{incident['id']}/investigation", headers=headers).json()

    assert [e["agent_name"] for e in body["executions"]] == graph.NODE_ORDER
    assert {e["status"] for e in body["executions"]} == {"COMPLETED"}
    assert all(e["started_at"] and e["finished_at"] for e in body["executions"])


def test_the_evidence_actually_collected_is_persisted(
    client, incident, headers, fake_llm, log_file
):
    start_investigation(client, incident["id"], headers)

    body = client.get(f"/incidents/{incident['id']}/investigation", headers=headers).json()
    collector = next(e for e in body["executions"] if e["agent_name"] == "evidence_collector")

    assert collector["output"]["evidence"][0]["request_id"] == "abc123"
    assert collector["output"]["evidence"][0]["endpoint"] == "POST /orders"


def test_the_report_itself_is_not_duplicated_into_the_execution_row(
    client, incident, headers, fake_llm, log_file
):
    start_investigation(client, incident["id"], headers)

    body = client.get(f"/incidents/{incident['id']}/investigation", headers=headers).json()
    report_node = next(e for e in body["executions"] if e["agent_name"] == "report")

    assert set(report_node["output"]) == {"report_characters"}
    assert report_node["output"]["report_characters"] == len(body["report"])


def test_investigation_records_activity(client, incident, headers, fake_llm, log_file):
    start_investigation(client, incident["id"], headers)

    types = [
        entry["activity_type"]
        for entry in client.get(f"/incidents/{incident['id']}/activity", headers=headers).json()
    ]

    assert types == ["INCIDENT_CREATED", "INVESTIGATION_STARTED", "INVESTIGATION_COMPLETED"]


def test_a_failing_agent_marks_the_run_failed(client, incident, headers, monkeypatch, log_file):
    def exploding_llm():
        raise RuntimeError("anthropic is unavailable")

    monkeypatch.setattr(graph, "get_llm", exploding_llm)

    started = start_investigation(client, incident["id"], headers)
    assert started.status_code == 202

    body = client.get(f"/incidents/{incident['id']}/investigation", headers=headers).json()

    assert body["status"] == "FAILED"
    assert "anthropic is unavailable" in body["error"]
    assert body["report"] is None
    assert [(e["agent_name"], e["status"]) for e in body["executions"]] == [("planner", "FAILED")]


def test_a_failure_records_activity_and_leaves_the_incident_usable(
    client, incident, headers, monkeypatch, log_file
):
    monkeypatch.setattr(graph, "get_llm", lambda: (_ for _ in ()).throw(RuntimeError("down")))

    start_investigation(client, incident["id"], headers)

    types = [
        entry["activity_type"]
        for entry in client.get(f"/incidents/{incident['id']}/activity", headers=headers).json()
    ]

    assert types[-1] == "INVESTIGATION_FAILED"
    assert client.patch(
        f"/incidents/{incident['id']}/status", json={"status": "INVESTIGATING"}, headers=headers
    ).status_code == 200


def test_a_failed_run_can_be_retried(client, incident, headers, monkeypatch, fake_llm, log_file):
    monkeypatch.setattr(graph, "get_llm", lambda: (_ for _ in ()).throw(RuntimeError("down")))
    start_investigation(client, incident["id"], headers)

    monkeypatch.setattr(graph, "get_llm", FakeLLM)
    retried = start_investigation(client, incident["id"], headers)

    assert retried.status_code == 202

    runs = client.get(f"/incidents/{incident['id']}/investigations", headers=headers).json()

    assert [run["status"] for run in runs] == ["COMPLETED", "FAILED"]


def test_a_second_investigation_is_rejected_while_one_is_pending(
    client, incident, headers, db, log_file
):
    """A run left PENDING or RUNNING blocks a duplicate, so retries cannot double-report."""
    from app.models.workflow import RunStatus, WorkflowRun

    db.add(
        WorkflowRun(
            incident_id=incident["id"], triggered_by="test", status=RunStatus.RUNNING
        )
    )
    db.commit()

    response = start_investigation(client, incident["id"], headers)

    assert response.status_code == 409


def test_investigating_a_missing_incident_returns_404(client, headers):
    assert client.post("/incidents/404/investigate", headers=headers).status_code == 404


def test_investigation_for_an_incident_without_one_returns_404(client, incident, headers):
    response = client.get(f"/incidents/{incident['id']}/investigation", headers=headers)

    assert response.status_code == 404


def test_investigation_by_run_id(client, incident, headers, fake_llm, log_file):
    run = start_investigation(client, incident["id"], headers).json()

    body = client.get(f"/investigations/{run['id']}", headers=headers).json()

    assert body["id"] == run["id"]
    assert body["status"] == "COMPLETED"


def test_missing_run_id_returns_404(client, headers):
    assert client.get("/investigations/404", headers=headers).status_code == 404


def test_investigation_endpoints_require_authentication(client, incident):
    assert client.post(f"/incidents/{incident['id']}/investigate").status_code == 401
    assert client.get(f"/incidents/{incident['id']}/investigation").status_code == 401
    assert client.get("/investigations/1").status_code == 401


def test_report_is_honest_when_there_is_no_evidence(
    client, incident, headers, fake_llm, tmp_path, monkeypatch
):
    monkeypatch.setattr(settings, "dummycommerce_log_path", str(tmp_path / "absent.jsonl"))

    start_investigation(client, incident["id"], headers)

    body = client.get(f"/incidents/{incident['id']}/investigation", headers=headers).json()

    assert body["status"] == "COMPLETED"
    assert "0 log record(s)" in body["report"]
    assert "no log records matched" in body["report"]


def test_the_graph_is_the_documented_pipeline():
    assert graph.NODE_ORDER == [
        "planner",
        "evidence_collector",
        "root_cause",
        "fix_recommendation",
        "report",
    ]


@pytest.mark.parametrize(
    ("provider", "key_setting", "expected"),
    [
        ("gemini", "google_api_key", "GOOGLE_API_KEY"),
        ("anthropic", "anthropic_api_key", "ANTHROPIC_API_KEY"),
    ],
)
def test_get_llm_refuses_to_run_without_a_key(monkeypatch, provider, key_setting, expected):
    monkeypatch.setattr(settings, "llm_provider", provider)
    monkeypatch.setattr(settings, key_setting, None)

    with pytest.raises(RuntimeError, match=expected):
        graph.get_llm()


# --- watching a run as it happens ------------------------------------------------------


def test_each_agents_reasoning_is_stored_with_its_execution(
    client, incident, headers, fake_llm, log_file
):
    from tests.fake_llm import FAKE_THINKING

    start_investigation(client, incident["id"], headers)

    body = client.get(f"/incidents/{incident['id']}/investigation", headers=headers).json()
    thinking = {
        e["agent_name"]: (e["output"] or {}).get("thinking")
        for e in body["executions"]
    }

    assert thinking["planner"] == FAKE_THINKING
    assert thinking["root_cause"] == FAKE_THINKING
    assert thinking["fix_recommendation"] == FAKE_THINKING
    assert thinking["evidence_collector"] is None, "a plain Python node does not think"


def test_reasoning_can_be_turned_off(client, incident, headers, fake_llm, log_file, monkeypatch):
    monkeypatch.setattr(settings, "llm_show_thinking", False)

    start_investigation(client, incident["id"], headers)

    body = client.get(f"/incidents/{incident['id']}/investigation", headers=headers).json()

    assert all("thinking" not in (e["output"] or {}) for e in body["executions"])


def test_stored_reasoning_is_capped(client, incident, headers, fake_llm, log_file, monkeypatch):
    monkeypatch.setattr(settings, "llm_thinking_max_chars", 10)

    start_investigation(client, incident["id"], headers)

    body = client.get(f"/incidents/{incident['id']}/investigation", headers=headers).json()
    planner = next(e for e in body["executions"] if e["agent_name"] == "planner")

    assert len(planner["output"]["thinking"]) == 10


def test_progress_is_logged_for_every_agent(client, incident, headers, fake_llm, log_file, caplog):
    with caplog.at_level("INFO", logger="app.services.investigation_service"):
        start_investigation(client, incident["id"], headers)

    logged = "\n".join(caplog.messages)

    for node in graph.NODE_ORDER:
        assert node in logged, f"{node} produced no progress line"


def test_progress_lines_say_what_each_agent_found():
    from app.services.investigation_service import InvestigationService as S

    assert "2 step(s)" in S._progress_summary("planner", {"plan": {"steps": ["a", "b"]}})
    assert "3 log record(s)" in S._progress_summary("evidence_collector", {"evidence": [1, 2, 3]})
    assert "[low]" in S._progress_summary(
        "root_cause", {"root_cause": {"confidence": "low", "likely_cause": "db down"}}
    )
    assert "1 action(s)" in S._progress_summary(
        "fix_recommendation", {"recommendations": {"actions": ["restart"]}}
    )
    assert "report assembled" in S._progress_summary("report", {"report": "x" * 5})


def test_the_run_is_observable_while_it_is_still_going(
    client, incident, headers, log_file, monkeypatch
):
    """An engineer polling mid-run sees RUNNING, and the agents that have finished so far."""
    gate = threading.Event()

    class SlowLLM(FakeLLM):
        """Blocks on the root_cause call, after the planner has already reported."""

        def with_structured_output(self, schema, include_raw=False):
            if schema is RootCause:
                gate.wait(20)
            return super().with_structured_output(schema, include_raw)

    monkeypatch.setattr(graph, "get_llm", SlowLLM)

    try:
        client.post(f"/incidents/{incident['id']}/investigate", headers=headers)

        for _ in range(100):
            mid = client.get(
                f"/incidents/{incident['id']}/investigation", headers=headers
            ).json()
            if any(e["agent_name"] == "evidence_collector" for e in mid["executions"]):
                break
            time.sleep(0.05)
    finally:
        gate.set()

    assert mid["status"] == "RUNNING"
    assert mid["report"] is None
    assert [e["agent_name"] for e in mid["executions"]] == ["planner", "evidence_collector"]
