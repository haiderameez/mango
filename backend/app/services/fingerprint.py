"""Stable failure fingerprints that ignore volatile values in log messages."""
import hashlib
import ipaddress
import re

UUID_PATTERN = re.compile(
    r"\b[0-9a-f]{8}-[0-9a-f]{4}-[1-8][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}\b",
    re.IGNORECASE,
)
TIMESTAMP_PATTERN = re.compile(
    r"\b\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:?\d{2})?\b",
    re.IGNORECASE,
)
IP_PATTERN = re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}\b")
NUMBER_PATTERN = re.compile(r"(?<!\d)\d+(?:\.\d+)?(?!\d)")


def normalize_message(message: str) -> str:
    normalized = UUID_PATTERN.sub("<uuid>", message)
    normalized = TIMESTAMP_PATTERN.sub("<timestamp>", normalized)

    def replace_ip(match: re.Match) -> str:
        try:
            ipaddress.ip_address(match.group())
        except ValueError:
            return match.group()
        return "<ip>"

    normalized = IP_PATTERN.sub(replace_ip, normalized)
    normalized = NUMBER_PATTERN.sub("<n>", normalized)
    return " ".join(normalized.lower().split())


def failure_fingerprint(service: str, message: str, error_type: str | None = None) -> str:
    parts = (
        service.strip().lower(),
        normalize_message(message),
        (error_type or "").strip().lower(),
    )
    return hashlib.sha256("\0".join(parts).encode("utf-8")).hexdigest()
