"""The LangGraph investigation workflow.

Planner -> Evidence Collector -> Root Cause -> Fix Recommendation -> Report

Log retrieval stays in ordinary Python (app.services.evidence); the model only ever sees
the bounded, scrubbed evidence that the collector returns.
"""
import json
import logging
import re
from datetime import datetime
from functools import lru_cache
from typing import TypedDict

from langchain_core.rate_limiters import InMemoryRateLimiter
from langgraph.graph import END, StateGraph

from app.ai import quota
from app.ai.schemas import Plan, Recommendations, RootCause
from app.core.config import settings
from app.core.exceptions import LlmQuotaExhaustedError, LlmRateLimitedError
from app.services import evidence

logger = logging.getLogger("mango.investigation")

NODE_ORDER = ["planner", "evidence_collector", "root_cause", "fix_recommendation", "report"]

# How many provider requests one investigation needs. evidence_collector and report are
# plain Python and cost nothing.
LLM_CALLS_PER_RUN = 3

GROUNDING_RULES = (
    "Use only the evidence supplied in this message. Never invent log lines, timestamps or "
    "metrics. If the evidence is insufficient to identify a cause, say so plainly and set a "
    "low confidence instead of guessing."
)


class InvestigationState(TypedDict, total=False):
    incident: dict
    plan: dict
    evidence: list[dict]
    root_cause: dict
    recommendations: dict
    report: str


@lru_cache(maxsize=4)
def _rate_limiter(requests_per_minute: int) -> InMemoryRateLimiter:
    """One limiter shared by every agent and every investigation, so the whole application
    stays under the provider's per-minute limit. A call waits for its turn instead of being
    sent and rejected.

    max_bucket_size=1 means no bursting: a free tier counts a burst like any other traffic.
    """
    return InMemoryRateLimiter(
        requests_per_second=requests_per_minute / 60,
        check_every_n_seconds=0.5,
        max_bucket_size=1,
    )


def get_llm():
    """The chat model used by every agent node. Patched out in tests."""
    limiter = _rate_limiter(settings.llm_requests_per_minute)

    if settings.llm_provider == "gemini":
        if not settings.google_api_key:
            raise RuntimeError(
                "GOOGLE_API_KEY is not configured, so an AI investigation cannot run."
            )

        from langchain_google_genai import ChatGoogleGenerativeAI

        return ChatGoogleGenerativeAI(
            model=settings.gemini_model,
            google_api_key=settings.google_api_key,
            temperature=0,
            timeout=120,
            max_retries=settings.llm_max_retries,
            rate_limiter=limiter,
            include_thoughts=settings.llm_show_thinking,
        )

    if not settings.anthropic_api_key:
        raise RuntimeError(
            "ANTHROPIC_API_KEY is not configured, so an AI investigation cannot run."
        )

    from langchain_anthropic import ChatAnthropic

    return ChatAnthropic(
        model=settings.anthropic_model,
        api_key=settings.anthropic_api_key,
        temperature=0,
        timeout=120,
        max_retries=settings.llm_max_retries,
        rate_limiter=limiter,
    )


def _retry_after_seconds(error: Exception) -> float:
    """The provider's own backoff hint, e.g. "retryDelay": "21s"."""
    match = re.search(r"retry[-_ ]?delay['\"]?[:= ]+['\"]?(\d+(?:\.\d+)?)s", str(error), re.I)

    return float(match.group(1)) if match else settings.llm_cooldown_seconds


def is_rate_limited(error: Exception) -> bool:
    text = str(error)

    return getattr(error, "code", None) == 429 or "429" in text or "RESOURCE_EXHAUSTED" in text


def _ask(schema, prompt: str):
    """One provider request, charged against today's budget before it is sent."""
    if quota.is_cooling_down():
        raise LlmRateLimitedError(
            f"The provider asked us to back off; {quota.cooldown_remaining():.0f}s left."
        )

    if not quota.consume():
        raise LlmQuotaExhaustedError(
            f"The daily LLM request budget ({settings.llm_requests_per_day}) is spent. "
            f"It resets in {quota.seconds_until_reset() / 3600:.1f} hours."
        )

    try:
        return _invoke(schema, prompt)
    except Exception as error:
        if not is_rate_limited(error):
            raise

        # Our configured budget was wrong, or something else is spending the same key.
        # The provider is the authority: stop sending until it says we may again.
        quota.start_cooldown(_retry_after_seconds(error))

        raise LlmRateLimitedError(
            f"The provider rate-limited this request: {error}"
        ) from error


def _thinking_from(message) -> str:
    """Gemini's thought summary, if the model returned one."""
    content = getattr(message, "content", None)

    if isinstance(content, list):
        thoughts = [
            block.get("thinking") or block.get("text", "")
            for block in content
            if isinstance(block, dict)
            and (block.get("thinking") or block.get("type") == "thinking")
        ]
        return "\n".join(t for t in thoughts if t).strip()

    return ""


def _invoke(schema, prompt: str):
    """Call the model and surface its reasoning as it happens."""
    if not settings.llm_show_thinking:
        return get_llm().with_structured_output(schema).invoke(prompt)

    result = get_llm().with_structured_output(schema, include_raw=True).invoke(prompt)

    if result.get("parsing_error"):
        raise result["parsing_error"]

    thinking = _thinking_from(result.get("raw"))

    if thinking:
        logger.info("    thinking: %s", thinking.replace("\n", "\n              "))
        _LAST_THINKING.append(thinking[: settings.llm_thinking_max_chars])

    return result["parsed"]


# The most recent agent's thought summary, picked up by the node wrappers below so it can
# be stored with that agent's execution record.
_LAST_THINKING: list[str] = []


def take_thinking() -> str | None:
    return _LAST_THINKING.pop() if _LAST_THINKING else None


def planner(state: InvestigationState) -> InvestigationState:
    plan = _ask(
        Plan,
        "You are an SRE planning the investigation of a production incident.\n"
        f"Incident: {json.dumps(state['incident'])}\n\n"
        "Decide what should be investigated and which single keyword would best narrow a "
        "search of the application's error logs.",
    )
    return {"plan": plan.model_dump()}


def evidence_collector(state: InvestigationState) -> InvestigationState:
    created_at = datetime.fromisoformat(state["incident"]["created_at"])
    keyword = (state.get("plan") or {}).get("log_keyword")
    return {"evidence": evidence.collect(created_at, keyword=keyword)}


def root_cause(state: InvestigationState) -> InvestigationState:
    analysis = _ask(
        RootCause,
        "You are an SRE diagnosing a production incident.\n"
        f"Incident: {json.dumps(state['incident'])}\n"
        f"Investigation plan: {json.dumps(state.get('plan') or {})}\n"
        f"Evidence (application log records): {json.dumps(state.get('evidence') or [])}\n\n"
        f"{GROUNDING_RULES}",
    )
    return {"root_cause": analysis.model_dump()}


def fix_recommendation(state: InvestigationState) -> InvestigationState:
    recommendations = _ask(
        Recommendations,
        "You are an SRE recommending corrective actions for a production incident.\n"
        f"Incident: {json.dumps(state['incident'])}\n"
        f"Diagnosis: {json.dumps(state.get('root_cause') or {})}\n"
        f"Evidence: {json.dumps(state.get('evidence') or [])}\n\n"
        "Recommend actions an engineer will review and apply themselves. Do not propose "
        "anything that would be executed automatically against production.\n"
        f"{GROUNDING_RULES}",
    )
    return {"recommendations": recommendations.model_dump()}


def _bullets(items: list[str], empty: str = "_none_") -> str:
    return "\n".join(f"- {item}" for item in items) if items else empty


def _evidence_line(record: dict) -> str:
    line = "`{}` **{}** {}".format(
        record.get("timestamp", "?"),
        record.get("level", "?"),
        record.get("message", ""),
    )
    if record.get("endpoint"):
        line += f" - {record['endpoint']}"
    if record.get("request_id"):
        line += f" (request {record['request_id']})"
    if record.get("context"):
        line += "  " + " ".join(f"`{k}={v}`" for k, v in record["context"].items())
    return line


def report(state: InvestigationState) -> InvestigationState:
    """Assemble the final report. No model call: this is formatting, not analysis."""
    incident = state["incident"]
    plan = state.get("plan") or {}
    analysis = state.get("root_cause") or {}
    recommendations = state.get("recommendations") or {}
    records = state.get("evidence") or []

    text = f"""# Investigation report - incident #{incident["id"]}

**{incident["title"]}**

Severity {incident["severity"]} - status {incident["status"]} - opened {incident["created_at"]}

{incident.get("description") or "_no description_"}

## Investigation plan

{_bullets(plan.get("steps", []))}

{plan.get("rationale", "")}

## Evidence collected (facts)

{len(records)} log record(s) from the incident window.

{_bullets([_evidence_line(r) for r in records], "_no log records matched the incident window._")}

## Observed facts

{_bullets(analysis.get("observed_facts", []))}

## Likely root cause (model conclusion, needs validation)

{analysis.get("likely_cause", "_not determined_")}

**Confidence: {analysis.get("confidence", "unknown")}**

### Supporting evidence

{_bullets(analysis.get("supporting_evidence", []))}

### Missing or contradicting evidence

{_bullets(analysis.get("missing_or_contradicting", []))}

## Recommended actions (for an engineer to review)

{_bullets(recommendations.get("actions", []))}

### How to validate

{_bullets(recommendations.get("validation_steps", []))}

{recommendations.get("notes") or ""}
"""
    return {"report": text}


def build_graph(*, start_at: str | None = None):
    if start_at is not None and start_at not in NODE_ORDER:
        raise ValueError(f"Unknown investigation node: {start_at}")
    graph = StateGraph(InvestigationState)

    for name in NODE_ORDER:
        graph.add_node(name, globals()[name])

    graph.set_entry_point(start_at or NODE_ORDER[0])
    for current, following in zip(NODE_ORDER, NODE_ORDER[1:], strict=False):
        graph.add_edge(current, following)
    graph.add_edge(NODE_ORDER[-1], END)

    return graph.compile()
