"""The agents' model, faked: tests must never depend on a provider being reachable."""
from app.ai.schemas import Plan, Recommendations, RootCause

FAKE_RESPONSES = {
    Plan: Plan(
        steps=["Read the order service error logs", "Check the orders-db connection"],
        log_keyword="orders",
        rationale="The incident points at order creation.",
    ),
    RootCause: RootCause(
        observed_facts=["POST /orders logged connection refused to orders-db"],
        likely_cause="orders-db is refusing connections",
        supporting_evidence=["could not connect to server: Connection refused"],
        missing_or_contradicting=["No database-side logs were available"],
        confidence="medium",
    ),
    Recommendations: Recommendations(
        actions=["Check whether orders-db is running", "Verify the connection pool settings"],
        validation_steps=["Retry POST /orders once the database accepts connections"],
        notes=None,
    ),
}


FAKE_THINKING = "Checking the endpoint in the evidence, then the error type."


class FakeMessage:
    """Shaped like an AIMessage carrying a Gemini thought summary."""

    def __init__(self, thinking):
        self.content = [
            {"type": "thinking", "thinking": thinking},
            {"type": "text", "text": "{}"},
        ]


class FakeStructuredModel:
    def __init__(self, schema, include_raw=False):
        self.schema = schema
        self.include_raw = include_raw

    def invoke(self, prompt):
        assert isinstance(prompt, str) and prompt
        parsed = FAKE_RESPONSES[self.schema]

        if not self.include_raw:
            return parsed

        return {"raw": FakeMessage(FAKE_THINKING), "parsed": parsed, "parsing_error": None}


class FakeLLM:
    def with_structured_output(self, schema, include_raw=False):
        return FakeStructuredModel(schema, include_raw)
