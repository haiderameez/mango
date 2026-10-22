"""Celery worker-only fake model that pauses its first root-cause call for a crash probe."""
import os
import time

import redis

from app.ai import graph
from app.ai.schemas import Plan, Recommendations, RootCause
from app.core.config import settings

_client = redis.Redis.from_url(settings.redis_url)
_RESPONSES = {
    Plan: Plan(
        steps=["Read order service logs"],
        log_keyword="orders",
        rationale="The incident is synthetic.",
    ),
    RootCause: RootCause(
        observed_facts=["Synthetic order failure"],
        likely_cause="Synthetic database connection failure",
        supporting_evidence=["Synthetic connection refused"],
        missing_or_contradicting=[],
        confidence="medium",
    ),
    Recommendations: Recommendations(
        actions=["Check the synthetic database"],
        validation_steps=["Retry the synthetic request"],
        notes=None,
    ),
}


class _FakeMessage:
    content = [
        {"type": "thinking", "thinking": "Using only the synthetic test fixture."},
        {"type": "text", "text": "{}"},
    ]


class _StructuredFake:
    def __init__(self, schema, include_raw):
        self.schema = schema
        self.include_raw = include_raw

    def invoke(self, prompt):
        _client.incr("mango:worker-loss:fake-calls")
        if self.schema is RootCause:
            attempt = _client.incr("mango:worker-loss:root-cause-attempts")
            if attempt == 1:
                _client.set("mango:worker-loss:root-cause-pid", os.getpid())
                _client.set("mango:worker-loss:root-cause-started", "1")
                while True:
                    time.sleep(1)

        parsed = _RESPONSES[self.schema]
        if not self.include_raw:
            return parsed
        return {"raw": _FakeMessage(), "parsed": parsed, "parsing_error": None}


class _FakeLLM:
    def with_structured_output(self, schema, include_raw=False):
        return _StructuredFake(schema, include_raw)


settings.llm_requests_per_day = 100
settings.llm_requests_per_minute = 600
settings.incident_history_enabled = False
graph.get_llm = _FakeLLM
