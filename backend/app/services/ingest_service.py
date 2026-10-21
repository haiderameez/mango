"""Service authentication, bounded JSONL parsing and rule-based incident detection."""
import gzip
import hashlib
import json
import logging
import re
import zlib
from datetime import UTC, datetime, timedelta

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.notifications import notify_incident_created
from app.models.activity import ActivityType
from app.models.incident import Incident, IncidentGroup, SeverityLevel
from app.models.ingest import DetectionRule, LogRecord, ServiceIngestKey
from app.repositories.activity_repository import ActivityRepository
from app.repositories.incident_repository import IncidentRepository
from app.repositories.ingest_repository import IngestRepository
from app.services.fingerprint import failure_fingerprint

logger = logging.getLogger(__name__)

MAX_BATCH_RECORDS = 500
MAX_UNCOMPRESSED_BYTES = 5_000_000
MAX_MESSAGE_LENGTH = 1000
MAX_CONTEXT_FIELDS = 32
SENSITIVE_KEYS = {"password", "token", "secret", "authorization", "api_key", "cookie"}
ERROR_LEVELS = {"ERROR", "CRITICAL"}


class IngestPayloadError(ValueError):
    pass


def _safe_context(record: dict) -> dict:
    excluded = {
        "timestamp", "ts", "service", "level", "message", "request_id",
        "endpoint",
    }
    context = {}
    for name, value in record.items():
        if name.lower() in excluded or any(secret in name.lower() for secret in SENSITIVE_KEYS):
            continue
        if not isinstance(value, (str, int, float, bool)):
            continue
        context[name[:128]] = value[:200] if isinstance(value, str) else value
        if len(context) >= MAX_CONTEXT_FIELDS:
            break
    return context


def parse_jsonl(payload: bytes, *, compressed: bool = False) -> list[dict]:
    """Parse at most 500 bounded JSON objects; malformed rows are rejected as a batch."""
    if compressed:
        inflater = zlib.decompressobj(16 + zlib.MAX_WBITS)
        data = inflater.decompress(payload, MAX_UNCOMPRESSED_BYTES + 1)
        if len(data) > MAX_UNCOMPRESSED_BYTES or inflater.unconsumed_tail:
            raise IngestPayloadError("Uncompressed batch exceeds 5 MB.")
        data += inflater.flush()
        if len(data) > MAX_UNCOMPRESSED_BYTES:
            raise IngestPayloadError("Uncompressed batch exceeds 5 MB.")
        if not inflater.eof:
            raise IngestPayloadError("Compressed batch is incomplete or invalid.")
    else:
        data = payload
        if len(data) > MAX_UNCOMPRESSED_BYTES:
            raise IngestPayloadError("Batch exceeds 5 MB.")
    if not data:
        raise IngestPayloadError("Batch cannot be empty.")

    lines = data.splitlines()
    if len(lines) > MAX_BATCH_RECORDS:
        raise IngestPayloadError("A batch can contain at most 500 records.")
    records = []
    for line_number, line in enumerate(lines, start=1):
        if not line.strip():
            continue
        try:
            record = json.loads(line)
        except (UnicodeDecodeError, json.JSONDecodeError) as error:
            raise IngestPayloadError(f"Line {line_number} is not valid JSON.") from error
        if not isinstance(record, dict):
            raise IngestPayloadError(f"Line {line_number} must be a JSON object.")
        if not isinstance(record.get("service"), str) or not record["service"].strip():
            raise IngestPayloadError(f"Line {line_number} needs a service name.")
        if not isinstance(record.get("level"), str) or not record["level"].strip():
            raise IngestPayloadError(f"Line {line_number} needs a log level.")
        if not isinstance(record.get("message"), str):
            raise IngestPayloadError(f"Line {line_number} needs a message.")
        try:
            ts = datetime.fromisoformat(record.get("timestamp") or record.get("ts"))
        except (TypeError, ValueError) as error:
            raise IngestPayloadError(f"Line {line_number} needs an ISO timestamp.") from error
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=UTC)
        records.append({**record, "service": record["service"].strip()[:255],
                        "level": record["level"].strip().upper()[:32],
                        "message": record["message"][:MAX_MESSAGE_LENGTH],
                        "request_id": str(record["request_id"])
                        if record.get("request_id") is not None else None,
                        "ts": ts.astimezone(UTC), "context": _safe_context(record)})
    if not records:
        raise IngestPayloadError("Batch contains no log records.")
    return records


class IngestService:
    def __init__(self, db: Session):
        self.db = db
        self.repository = IngestRepository(db)
        self.incidents = IncidentRepository(db)
        self.activities = ActivityRepository(db)

    def authenticate(self, token: str) -> ServiceIngestKey | None:
        if not token or len(token) > 256:
            return None
        key_hash = hashlib.sha256(token.encode("utf-8")).hexdigest()
        return self.repository.get_key_by_hash(key_hash)

    @staticmethod
    def create_key(db: Session, service: str, created_by: int) -> str:
        """Persist a one-way password hash and return a new random key once."""
        import secrets

        token = secrets.token_urlsafe(32)
        IngestRepository(db).add_key(
            ServiceIngestKey(
                service=service,
                key_hash=hashlib.sha256(token.encode("utf-8")).hexdigest(),
                created_by=created_by,
            )
        )
        return token

    def process_batch(self, key_id: int, payload: bytes, compressed: bool = False) -> int:
        key = self.repository.get_active_key(key_id)
        if key is None:
            logger.warning("Discarding an ingest batch with an invalid or revoked service key.")
            return 0
        try:
            incoming = parse_jsonl(payload, compressed=compressed)
        except (IngestPayloadError, zlib.error, gzip.BadGzipFile, EOFError):
            logger.warning("Discarding malformed ingest batch for service %s.", key.service)
            return 0
        records = [
            LogRecord(service=item["service"], level=item["level"], message=item["message"],
                      context=item["context"], request_id=item["request_id"], ts=item["ts"])
            for item in incoming if item["service"] == key.service
        ]
        if not records:
            logger.warning("Ingest key service did not match any record; batch discarded.")
            return 0
        self.repository.add_records(records)
        self._detect(records, key.created_by)
        return len(records)

    def _detect(self, batch: list[LogRecord], created_by: int) -> None:
        by_service = {record.service for record in batch}
        batch_ids = {record.id for record in batch}
        now = max(record.ts for record in batch)
        handled_fingerprints = set()
        for rule in self.repository.get_active_rules():
            services = by_service if rule.service == "*" else by_service & {rule.service}
            for service in services:
                start = now - timedelta(seconds=rule.window_seconds)
                records = self.repository.get_window(
                    start, now, MAX_BATCH_RECORDS, service=service
                )
                matched = self._matches(rule, records)
                if matched:
                    groups: dict[str, list[LogRecord]] = {}
                    for record in matched:
                        error_type = record.context.get("error_type")
                        fingerprint = failure_fingerprint(service, record.message, error_type)
                        groups.setdefault(fingerprint, []).append(record)
                    for failure_records in groups.values():
                        fingerprint = failure_fingerprint(
                            service,
                            failure_records[0].message,
                            failure_records[0].context.get("error_type"),
                        )
                        if fingerprint in handled_fingerprints:
                            continue
                        handled_fingerprints.add(fingerprint)
                        new_count = sum(record.id in batch_ids for record in failure_records)
                        if new_count:
                            self._open_incident(
                                rule, service, failure_records, created_by, new_count=new_count
                            )

    @staticmethod
    def _matches(rule: DetectionRule, records: list[LogRecord]) -> list[LogRecord]:
        if not records:
            return []
        if rule.pattern == "error_rate":
            errors = [r for r in records if r.level.upper() in ERROR_LEVELS]
            return errors if len(errors) / len(records) * 100 > rule.threshold else []
        candidates = [
            r for r in records if rule.level == "*" or r.level.upper() == rule.level.upper()
        ]
        if rule.pattern:
            try:
                expression = re.compile(rule.pattern, re.IGNORECASE)
            except re.error:
                logger.error("Skipping detection rule %s with an invalid pattern.", rule.id)
                return []
            candidates = [
                r for r in candidates if expression.search(f"{r.level} {r.message}")
            ]
        return candidates if len(candidates) >= rule.threshold else []

    def _open_incident(
        self,
        rule: DetectionRule,
        service: str,
        matches: list[LogRecord],
        created_by: int,
        new_count: int | None = None,
    ) -> None:
        seen_at = max(record.ts for record in matches)
        error_type = matches[0].context.get("error_type")
        fingerprint = failure_fingerprint(service, matches[0].message, error_type)
        existing = self.incidents.get_open_by_fingerprint(fingerprint)
        if existing is not None:
            updated = self.incidents.increment_occurrence(
                existing.id, new_count or len(matches), seen_at
            )
            self.activities.record(
                incident_id=updated.id,
                activity_type=ActivityType.OCCURRENCE_DETECTED,
                user_id=created_by,
                detail=f"{new_count or len(matches)} occurrence(s); "
                       f"total {updated.occurrence_count}",
                commit=True,
            )
            return

        severity = SeverityLevel.CRITICAL if any(r.level == "CRITICAL" for r in matches) \
            else SeverityLevel.HIGH
        description = (
            f"Detection rule {rule.id} observed {len(matches)} matching record(s) for "
            f"{service} in {rule.window_seconds}s. First: {matches[-1].message[:300]}"
        )
        upstream_name = next((r.context.get("upstream_name") for r in matches
                              if r.context.get("upstream_name")), None)
        request_id = next((r.request_id for r in matches if r.request_id), None)
        try:
            incident = self.incidents.create(Incident(
                title=f"Detected {rule.level} log activity in {service}"[:255],
                description=description[:1000], severity=severity, created_by=created_by,
                fingerprint=fingerprint, occurrence_count=len(matches), last_seen_at=seen_at,
                service=service, request_id=request_id, upstream_name=upstream_name,
            ))
        except IntegrityError:
            self.db.rollback()
            existing = self.incidents.get_open_by_fingerprint(fingerprint)
            if existing is None:
                raise
            updated = self.incidents.increment_occurrence(
                existing.id, new_count or len(matches), seen_at
            )
            self.activities.record(
                incident_id=updated.id,
                activity_type=ActivityType.OCCURRENCE_DETECTED,
                user_id=created_by,
                detail=f"{new_count or len(matches)} occurrence(s); "
                       f"total {updated.occurrence_count}",
                commit=True,
            )
            return

        related = self.incidents.get_related(
            incident, seen_at - timedelta(minutes=5)
        )
        if related:
            group_ids = {item.group_id for item in related if item.group_id is not None}
            if group_ids:
                group_id = min(group_ids)
                self.incidents.merge_groups(group_ids, group_id)
            else:
                group = self.incidents.add_group(
                    IncidentGroup(root_service=related[0].service)
                )
                group_id = group.id
            self.incidents.set_group([incident.id, *(item.id for item in related)], group_id)
            self.activities.record(
                incident_id=incident.id,
                activity_type=ActivityType.INCIDENT_CORRELATED,
                user_id=created_by,
                detail=f"Correlated with {len(related)} incident(s) in group {group_id}",
                commit=True,
            )

        self.activities.record(
            incident_id=incident.id, activity_type=ActivityType.INCIDENT_CREATED,
            user_id=created_by, detail=f"Automatically detected by rule {rule.id}", commit=True,
        )
        try:
            notify_incident_created(incident)
        except Exception:  # notification failures cannot lose a detected incident
            logger.exception("Notification failed for detected incident %s", incident.id)
