"""The guards that keep a free-tier key under its limits: per-minute pacing, a persisted
daily budget, and a single-worker queue."""
import json
import threading
import time

import pytest

from app.ai import graph, quota
from app.core.config import settings
from app.core.exceptions import LlmQuotaExhaustedError, LlmRateLimitedError
from app.services.investigation_queue import InvestigationQueue
from tests.conftest import start_investigation
from tests.fake_llm import FakeLLM

AN_INCIDENT = {"id": 1, "title": "x", "created_at": "2026-10-12T00:00:00+00:00"}

# --- per-minute rate limiter ----------------------------------------------------------


def test_the_limiter_matches_the_configured_requests_per_minute():
    limiter = graph._rate_limiter(10)

    assert limiter.requests_per_second == pytest.approx(10 / 60)


def test_the_limiter_does_not_allow_bursting():
    assert graph._rate_limiter(30).max_bucket_size == 1


def test_every_agent_shares_one_limiter():
    """A shared limiter is what makes the whole process stay under the provider's limit."""
    assert graph._rate_limiter(10) is graph._rate_limiter(10)
    assert graph._rate_limiter(10) is not graph._rate_limiter(15)


def test_the_limiter_actually_paces_calls():
    limiter = graph._rate_limiter(120)  # 2 per second

    limiter.acquire(blocking=True)
    started = time.monotonic()
    limiter.acquire(blocking=True)

    assert time.monotonic() - started >= 0.4


def test_the_model_is_built_with_the_limiter_attached(monkeypatch):
    monkeypatch.setattr(settings, "llm_provider", "gemini")
    monkeypatch.setattr(settings, "google_api_key", "test-key")

    llm = graph.get_llm()

    assert llm.rate_limiter is graph._rate_limiter(settings.llm_requests_per_minute)
    assert llm.max_retries == settings.llm_max_retries


# --- daily budget ---------------------------------------------------------------------


def test_a_fresh_day_starts_with_the_whole_budget(monkeypatch):
    monkeypatch.setattr(settings, "llm_requests_per_day", 250)

    assert quota.used_today() == 0
    assert quota.remaining() == 250


def test_consuming_reduces_what_is_left(monkeypatch):
    monkeypatch.setattr(settings, "llm_requests_per_day", 10)

    assert quota.consume(3) is True
    assert quota.used_today() == 3
    assert quota.remaining() == 7


def test_the_budget_cannot_be_overspent(monkeypatch):
    monkeypatch.setattr(settings, "llm_requests_per_day", 5)

    assert quota.consume(4) is True
    assert quota.consume(2) is False
    assert quota.used_today() == 4, "a refused request must not be charged"


def test_spending_survives_a_restart(monkeypatch):
    """The count lives in a file, so restarting Mango cannot spend the day twice."""
    monkeypatch.setattr(settings, "llm_requests_per_day", 10)
    quota.consume(6)

    state = json.loads((pytest.importorskip("pathlib").Path(settings.llm_quota_file)).read_text())

    assert state["used"] == 6
    assert quota.remaining() == 4


def test_yesterdays_count_is_ignored(monkeypatch, tmp_path):
    path = tmp_path / "stale.json"
    path.write_text(json.dumps({"date": "2020-01-01", "used": 999}), encoding="utf-8")
    monkeypatch.setattr(settings, "llm_quota_file", str(path))
    monkeypatch.setattr(settings, "llm_requests_per_day", 10)

    assert quota.used_today() == 0
    assert quota.has_capacity(10)


def test_a_corrupt_quota_file_does_not_break_the_app(monkeypatch, tmp_path):
    path = tmp_path / "broken.json"
    path.write_text("{not json", encoding="utf-8")
    monkeypatch.setattr(settings, "llm_quota_file", str(path))

    assert quota.used_today() == 0
    assert quota.consume(1) is True


def test_has_capacity_reflects_the_remaining_budget(monkeypatch):
    monkeypatch.setattr(settings, "llm_requests_per_day", 3)
    quota.consume(2)

    assert quota.has_capacity(1)
    assert not quota.has_capacity(2)


def test_reset_is_within_a_day(monkeypatch):
    assert 0 < quota.seconds_until_reset() <= 24 * 3600


def test_concurrent_consumers_cannot_oversell_the_budget(monkeypatch):
    monkeypatch.setattr(settings, "llm_requests_per_day", 50)
    granted = []

    def spend():
        for _ in range(20):
            granted.append(quota.consume(1))

    threads = [threading.Thread(target=spend) for _ in range(5)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert sum(granted) == 50
    assert quota.used_today() == 50


# --- the budget guard in the call path ------------------------------------------------


def test_an_agent_call_charges_the_budget(monkeypatch):
    monkeypatch.setattr(graph, "get_llm", FakeLLM)
    monkeypatch.setattr(settings, "llm_requests_per_day", 10)

    graph.planner({"incident": AN_INCIDENT})

    assert quota.used_today() == 1


def test_an_agent_refuses_to_call_once_the_budget_is_spent(monkeypatch):
    monkeypatch.setattr(graph, "get_llm", lambda: pytest.fail("the provider must not be called"))
    monkeypatch.setattr(settings, "llm_requests_per_day", 1)
    quota.consume(1)

    with pytest.raises(LlmQuotaExhaustedError, match="resets in"):
        graph.planner({"incident": AN_INCIDENT})


def test_a_whole_run_costs_three_requests(client, incident, headers, fake_llm, log_file):
    start_investigation(client, incident["id"], headers)

    assert quota.used_today() == graph.LLM_CALLS_PER_RUN == 3


# --- the queue ------------------------------------------------------------------------


def test_runs_execute_one_at_a_time_in_order():
    """Serialising is the point: two parallel investigations would double the request rate."""
    order, concurrent, peak = [], 0, 0
    lock = threading.Lock()

    def runner(run_id):
        nonlocal concurrent, peak
        with lock:
            concurrent += 1
            peak = max(peak, concurrent)
        order.append(run_id)
        time.sleep(0.02)
        with lock:
            concurrent -= 1

    investigation_queue = InvestigationQueue(runner)
    for run_id in range(1, 6):
        investigation_queue.submit(run_id)

    assert investigation_queue.wait_idle(15)
    assert order == [1, 2, 3, 4, 5]
    assert peak == 1


def test_submit_reports_the_queue_depth():
    gate = threading.Event()
    investigation_queue = InvestigationQueue(lambda run_id: gate.wait(5))

    investigation_queue.submit(1)
    second = investigation_queue.submit(2)

    assert second >= 1
    gate.set()
    assert investigation_queue.wait_idle(15)
    assert investigation_queue.depth == 0


def test_one_failing_run_does_not_strand_the_queue():
    done = []

    def runner(run_id):
        if run_id == 1:
            raise RuntimeError("boom")
        done.append(run_id)

    investigation_queue = InvestigationQueue(runner)
    investigation_queue.submit(1)
    investigation_queue.submit(2)

    assert investigation_queue.wait_idle(15)
    assert done == [2]


def test_the_queue_holds_work_back_when_the_budget_is_spent(monkeypatch):
    """No request is sent and nothing fails: the run waits for the budget to reset."""
    monkeypatch.setattr(settings, "llm_requests_per_day", 2)
    quota.consume(2)

    ran = []
    investigation_queue = InvestigationQueue(
        lambda run_id: ran.append(run_id), recheck_seconds=0.1
    )
    investigation_queue.submit(1)

    assert not investigation_queue.wait_idle(1.0), "the run should still be held"
    assert ran == [], "no request may be sent while the budget is spent"

    # Once the budget is back, the held run goes through on its own.
    monkeypatch.setattr(settings, "llm_requests_per_day", 100)

    assert investigation_queue.wait_idle(15)
    assert ran == [1]


def test_the_quota_endpoint_reports_what_is_left(client, headers, monkeypatch):
    monkeypatch.setattr(settings, "llm_requests_per_day", 30)
    quota.consume(3)

    body = client.get("/investigations/quota", headers=headers).json()

    assert body["provider"] == settings.llm_provider
    assert body["requests_used_today"] == 3
    assert body["requests_remaining_today"] == 27
    assert body["investigations_affordable_today"] == 9
    assert body["queue_depth"] == 0
    assert body["seconds_until_reset"] > 0


def test_the_quota_endpoint_requires_authentication(client):
    assert client.get("/investigations/quota").status_code == 401


# --- reacting to a 429 the provider sends anyway ---------------------------------------


class RateLimited(Exception):
    """What a provider 429 looks like coming out of the SDK."""

    def __init__(self, message="429 RESOURCE_EXHAUSTED {'retryDelay': '21s'}"):
        super().__init__(message)
        self.code = 429


def exploding_llm(error):
    class _Model:
        def with_structured_output(self, schema, include_raw=False):
            return self

        def invoke(self, prompt):
            raise error

    return lambda: _Model()


@pytest.mark.parametrize(
    "error",
    [
        RateLimited(),
        Exception("429 Too Many Requests"),
        Exception("RESOURCE_EXHAUSTED: quota exceeded"),
    ],
)
def test_a_provider_429_is_recognised(error):
    assert graph.is_rate_limited(error)


def test_an_ordinary_failure_is_not_treated_as_a_429():
    assert not graph.is_rate_limited(ValueError("bad schema"))


def test_the_providers_own_backoff_hint_is_used():
    assert graph._retry_after_seconds(RateLimited()) == 21.0


def test_an_unhelpful_429_falls_back_to_the_configured_cooldown(monkeypatch):
    monkeypatch.setattr(settings, "llm_cooldown_seconds", 45)

    assert graph._retry_after_seconds(Exception("429")) == 45


def test_a_429_starts_a_cooldown(monkeypatch):
    monkeypatch.setattr(graph, "get_llm", exploding_llm(RateLimited()))

    with pytest.raises(LlmRateLimitedError):
        graph.planner({"incident": AN_INCIDENT})

    assert quota.is_cooling_down()
    assert 19 < quota.cooldown_remaining() <= 21
    quota.clear_cooldown()


def test_nothing_is_sent_while_cooling_down(monkeypatch):
    monkeypatch.setattr(graph, "get_llm", lambda: pytest.fail("the provider must not be called"))
    quota.start_cooldown(30)

    try:
        with pytest.raises(LlmRateLimitedError, match="back off"):
            graph.planner({"incident": AN_INCIDENT})
    finally:
        quota.clear_cooldown()


def test_a_cooldown_does_not_shorten_itself(monkeypatch):
    quota.start_cooldown(60)
    quota.start_cooldown(5)

    try:
        assert quota.cooldown_remaining() > 50
    finally:
        quota.clear_cooldown()


def test_the_queue_holds_everything_during_a_cooldown(monkeypatch):
    ran = []
    investigation_queue = InvestigationQueue(lambda run_id: ran.append(run_id), recheck_seconds=0.1)
    quota.start_cooldown(600)
    investigation_queue.submit(1)

    try:
        assert not investigation_queue.wait_idle(1.0), "the run should be held"
        assert ran == []
    finally:
        quota.clear_cooldown()

    assert investigation_queue.wait_idle(15)
    assert ran == [1]


def test_a_rate_limited_run_fails_without_losing_the_incident(
    client, incident, headers, monkeypatch, log_file
):
    monkeypatch.setattr(graph, "get_llm", exploding_llm(RateLimited()))

    try:
        start_investigation(client, incident["id"], headers)

        body = client.get(f"/incidents/{incident['id']}/investigation", headers=headers).json()

        assert body["status"] == "FAILED"
        assert "rate-limited" in body["error"]
        assert client.get(f"/incidents/{incident['id']}", headers=headers).status_code == 200
    finally:
        quota.clear_cooldown()
