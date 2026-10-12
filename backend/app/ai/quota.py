"""Daily request budget for the LLM provider.

Free tiers are capped per day, not just per minute, and the per-minute limiter cannot see
that. This keeps a persisted count so a restart cannot spend the day's budget twice, and so
Mango refuses to send a request rather than earning a 429.
"""
import json
import logging
import threading
import time
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from app.core.config import settings

logger = logging.getLogger(__name__)

# ponytail: one process, one lock. Two Mango processes sharing a key would each keep their
# own count, so give each its own quota file and split the limit, or move this to the DB.
_lock = threading.Lock()


def _zone() -> ZoneInfo:
    return ZoneInfo(settings.llm_quota_timezone)


def _today() -> str:
    return datetime.now(_zone()).date().isoformat()


def _read() -> dict:
    path = Path(settings.llm_quota_file)

    try:
        state = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {"date": _today(), "used": 0}

    if not isinstance(state, dict) or state.get("date") != _today():
        return {"date": _today(), "used": 0}

    return {"date": state["date"], "used": int(state.get("used", 0))}


def _write(state: dict) -> None:
    path = Path(settings.llm_quota_file)

    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(state), encoding="utf-8")
    except OSError:
        logger.exception("Could not persist the LLM daily quota to %s", path)


def used_today() -> int:
    with _lock:
        return _read()["used"]


def remaining() -> int:
    return max(settings.llm_requests_per_day - used_today(), 0)


def has_capacity(requests: int = 1) -> bool:
    return remaining() >= requests


def consume(requests: int = 1) -> bool:
    """Spend part of today's budget. False means the budget is gone and nothing was spent."""
    with _lock:
        state = _read()

        if state["used"] + requests > settings.llm_requests_per_day:
            return False

        state["used"] += requests
        _write(state)

        return True


def seconds_until_reset() -> float:
    """Until the provider's daily counters roll over (midnight in the quota timezone)."""
    now = datetime.now(_zone())
    midnight = datetime.combine(now.date() + timedelta(days=1), datetime.min.time(), _zone())

    return max((midnight - now).total_seconds(), 0.0)


# --- provider cooldown ----------------------------------------------------------------
# The configured daily budget is our guess at the provider's limit. If the provider
# disagrees and returns a 429, that is the only authoritative signal we get: stop sending
# until it says we may again, instead of retrying into the same wall.
_cooldown_until = 0.0


def start_cooldown(seconds: float) -> None:
    global _cooldown_until

    with _lock:
        _cooldown_until = max(_cooldown_until, time.monotonic() + seconds)

    logger.warning("Provider asked us to back off. Pausing LLM traffic for %.0fs.", seconds)


def cooldown_remaining() -> float:
    with _lock:
        return max(_cooldown_until - time.monotonic(), 0.0)


def is_cooling_down() -> bool:
    return cooldown_remaining() > 0


def clear_cooldown() -> None:
    global _cooldown_until

    with _lock:
        _cooldown_until = 0.0
