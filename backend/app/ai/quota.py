"""Daily request budget for the LLM provider.

Free tiers are capped per day, not just per minute, and the per-minute limiter cannot see
that. This keeps a persisted count so a restart cannot spend the day's budget twice, and so
Mango refuses to send a request rather than earning a 429.
"""
import logging
import threading
import time
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import redis

from app.core.config import settings
from app.database.session import SessionLocal
from app.repositories.quota_repository import QuotaRepository

logger = logging.getLogger(__name__)
_redis = redis.Redis.from_url(settings.redis_url, decode_responses=True)
_RATE_SLOT_SCRIPT = (
    "local clock = redis.call('TIME'); "
    "local now = tonumber(clock[1]) + tonumber(clock[2]) / 1000000; "
    "local interval = tonumber(ARGV[1]); "
    "local next_at = tonumber(redis.call('GET', KEYS[1]) or '0'); "
    "if next_at <= now then "
    "redis.call('SET', KEYS[1], now + interval, 'PX', math.ceil(interval * 2000)); "
    "return 0; end; return next_at - now"
)

# This lock avoids needless SQLite contention in tests. PostgreSQL's conditional upsert is
# the cross-process authority in production.
_lock = threading.Lock()


def _zone() -> ZoneInfo:
    return ZoneInfo(settings.llm_quota_timezone)


def _today() -> str:
    return datetime.now(_zone()).date().isoformat()


def used_today() -> int:
    with _lock:
        with SessionLocal() as db:
            return QuotaRepository(db).used(_today())


def remaining() -> int:
    return max(settings.llm_requests_per_day - used_today(), 0)


def has_capacity(requests: int = 1) -> bool:
    return remaining() >= requests


def consume(requests: int = 1) -> bool:
    """Spend part of today's budget. False means the budget is gone and nothing was spent."""
    with _lock:
        with SessionLocal() as db:
            return QuotaRepository(db).consume(
                _today(), requests, settings.llm_requests_per_day
            )


def wait_for_rate_slot(model_name: str | None = None) -> None:
    """Pace provider calls across every worker sharing the Redis broker."""
    interval = 60 / max(settings.llm_requests_per_minute, 1)
    model = model_name or {
        "gemini": settings.gemini_model,
        "anthropic": settings.anthropic_model,
        "openrouter": settings.openrouter_model,
    }[settings.llm_provider]
    key = f"mango:llm:next:{settings.llm_provider}:{model}"
    while True:
        wait = float(_redis.eval(_RATE_SLOT_SCRIPT, 1, key, interval))
        if wait <= 0:
            return
        time.sleep(wait)


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
