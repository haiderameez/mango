from typing import Literal

from pydantic import BaseModel, Field


class Plan(BaseModel):
    """What the investigation should look at."""

    steps: list[str] = Field(description="Ordered investigation steps, at most five.")
    log_keyword: str | None = Field(
        default=None,
        description="A single keyword to narrow the log search, e.g. an endpoint or error type.",
    )
    rationale: str = Field(description="Why these steps, in one or two sentences.")


class RootCause(BaseModel):
    """A diagnosis that stays tied to the evidence it was given."""

    observed_facts: list[str] = Field(description="Facts taken only from the supplied evidence.")
    likely_cause: str = Field(description="The most likely cause, or that it cannot be determined.")
    supporting_evidence: list[str] = Field(
        description="The specific log messages that support it, quoted as readable text "
        "with their timestamp, not as raw JSON.",
    )
    missing_or_contradicting: list[str] = Field(
        description="Evidence that contradicts the diagnosis, or that is missing and would "
        "confirm it.",
    )
    confidence: Literal["low", "medium", "high"]


class Recommendations(BaseModel):
    """Corrective actions for a human to review, never to apply automatically."""

    actions: list[str] = Field(description="Practical corrective actions, most important first.")
    validation_steps: list[str] = Field(description="How an engineer can confirm the diagnosis.")
    notes: str | None = None
