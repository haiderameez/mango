"""Evidence collection: the only path between an investigation and raw diagnostic data.

The single source for v1 is the JSONL application log DummyCommerce writes. Results are
bounded and scrubbed before they can reach a prompt.
"""
import json
import logging
from datetime import UTC, datetime, timedelta
from pathlib import Path

from app.core.config import settings

logger = logging.getLogger(__name__)

SENSITIVE_KEYS = {"password", "token", "secret", "authorization", "api_key", "cookie"}

KEPT_FIELDS = ("timestamp", "level", "message", "endpoint", "request_id", "error_type", "service")

# Beyond the known fields, an application logs its own diagnostics (retry counts, pool
# depth, query plans). Those are the signal an investigation needs, so they are kept - but
# bounded, scalars only, and never anything that looks like a credential.
MAX_CONTEXT_FIELDS = 8
MAX_VALUE_LENGTH = 200


def _parse_timestamp(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)


def _context(record: dict) -> dict:
    extra = {}

    for key, value in record.items():
        if key in KEPT_FIELDS or key.lower() in SENSITIVE_KEYS:
            continue
        if not isinstance(value, str | int | float | bool):
            continue  # no nested blobs: they are unbounded and rarely diagnostic

        extra[key] = value[:MAX_VALUE_LENGTH] if isinstance(value, str) else value

        if len(extra) == MAX_CONTEXT_FIELDS:
            break

    return extra


def _normalize(record: dict) -> dict:
    evidence = {field: record.get(field) for field in KEPT_FIELDS if record.get(field) is not None}
    evidence.setdefault("source", record.get("service") or "dummycommerce")

    if isinstance(evidence.get("message"), str):
        evidence["message"] = evidence["message"][:MAX_VALUE_LENGTH * 4]

    context = _context(record)

    if context:
        evidence["context"] = context

    return evidence


def read_log_records(log_path: str | None = None) -> list[dict]:
    """Every parseable record in the log file, oldest first. Unreadable file -> no evidence."""
    path = Path(log_path or settings.dummycommerce_log_path)

    if not path.is_file():
        logger.warning("Evidence log file not found: %s", path)
        return []

    records = []
    with path.open(encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            try:
                record = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(record, dict):
                records.append({k: v for k, v in record.items() if k.lower() not in SENSITIVE_KEYS})

    return records


def collect(
    incident_created_at: datetime,
    keyword: str | None = None,
    log_path: str | None = None,
) -> list[dict]:
    """Log records around the incident, newest first, capped. Errors and warnings only,
    unless the filter leaves nothing, in which case the raw window is returned."""
    if incident_created_at.tzinfo is None:
        incident_created_at = incident_created_at.replace(tzinfo=UTC)

    window_start = incident_created_at - timedelta(minutes=settings.evidence_window_minutes)
    window_end = incident_created_at + timedelta(minutes=1)

    in_window = []
    for record in read_log_records(log_path):
        timestamp = _parse_timestamp(record.get("timestamp"))
        if timestamp is None or not (window_start <= timestamp <= window_end):
            continue
        in_window.append((timestamp, record))

    in_window.sort(key=lambda item: item[0], reverse=True)
    candidates = [record for _, record in in_window]

    levels = {"ERROR", "CRITICAL", "WARNING"}
    problems = [r for r in candidates if str(r.get("level", "")).upper() in levels]
    selected = problems or candidates

    if keyword:
        matched = [r for r in selected if keyword.lower() in json.dumps(r).lower()]
        selected = matched or selected

    return [_normalize(record) for record in selected[: settings.evidence_max_records]]
