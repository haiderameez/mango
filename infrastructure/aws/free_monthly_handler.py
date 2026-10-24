"""Small DynamoDB incident API for the AWS recurring-free-allowance deployment."""

from __future__ import annotations

import base64
import hmac
import json
import os
import re
import uuid
from datetime import UTC, datetime
from typing import Any

MAX_BODY_BYTES = 32 * 1024
MAX_LIST_LIMIT = 20
MAX_INCIDENTS = 10_000
SEVERITIES = {"LOW", "MEDIUM", "HIGH", "CRITICAL"}
TRANSITIONS = {"INVESTIGATING": "OPEN", "RESOLVED": "INVESTIGATING"}
INCIDENT_ID_PATTERN = re.compile(r"^[0-9a-f]{32}$")


def _response(status: int, body: dict[str, Any]) -> dict[str, Any]:
    return {
        "statusCode": status,
        "headers": {"content-type": "application/json; charset=utf-8", "cache-control": "no-store"},
        "body": json.dumps(body, separators=(",", ":")),
    }


def _table():
    import boto3

    return boto3.resource("dynamodb").Table(os.environ["INCIDENTS_TABLE"])


def _authorized(event: dict[str, Any]) -> bool:
    expected = os.environ.get("MANGO_FREE_API_TOKEN", "")
    headers = {key.lower(): value for key, value in (event.get("headers") or {}).items()}
    supplied = headers.get("authorization", "")
    prefix = "Bearer "
    return len(expected) >= 32 and supplied.startswith(prefix) and hmac.compare_digest(
        supplied[len(prefix) :], expected
    )


def _body(event: dict[str, Any]) -> dict[str, Any]:
    raw = event.get("body") or "{}"
    if event.get("isBase64Encoded"):
        raw = base64.b64decode(raw, validate=True).decode("utf-8")
    if len(raw.encode("utf-8")) > MAX_BODY_BYTES:
        raise ValueError("Request body is too large.")
    value = json.loads(raw)
    if not isinstance(value, dict):
        raise ValueError("Request body must be a JSON object.")
    return value


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _incident_key(incident_id: str) -> dict[str, str]:
    return {"PK": f"INCIDENT#{incident_id}", "SK": "METADATA"}


def handler(event: dict[str, Any], _context: Any = None) -> dict[str, Any]:
    if not _authorized(event):
        return _response(401, {"detail": "A valid bearer token is required."})

    request = event.get("requestContext", {}).get("http", {})
    method = request.get("method", "GET").upper()
    path = request.get("path", "/")
    if method == "GET" and path == "/health":
        return _response(200, {"status": "ok", "service": "mango-free-monthly"})

    table = _table()

    if method == "POST" and path == "/incidents":
        try:
            body = _body(event)
        except (ValueError, UnicodeDecodeError, json.JSONDecodeError):
            return _response(400, {"detail": "Request body must be a small valid JSON object."})
        title = body.get("title")
        description = body.get("description", "")
        severity = body.get("severity", "MEDIUM")
        if not isinstance(title, str) or not title.strip() or len(title) > 160:
            return _response(422, {"detail": "title must contain 1 to 160 characters."})
        if not isinstance(description, str) or len(description) > 1000:
            return _response(422, {"detail": "description must be at most 1000 characters."})
        if not isinstance(severity, str) or severity not in SEVERITIES:
            return _response(422, {"detail": "severity must be LOW, MEDIUM, HIGH, or CRITICAL."})
        now = _now()
        incident = {
            **_incident_key(uuid.uuid4().hex),
            "IncidentId": "",
            "Title": title.strip(),
            "Description": description,
            "Severity": severity,
            "Status": "OPEN",
            "CreatedAt": now,
            "UpdatedAt": now,
        }
        incident["IncidentId"] = incident["PK"].removeprefix("INCIDENT#")
        try:
            table.update_item(
                Key={"PK": "SYSTEM", "SK": "INCIDENT_COUNT"},
                UpdateExpression="SET #count = if_not_exists(#count, :zero) + :one",
                ConditionExpression="attribute_not_exists(#count) OR #count < :limit",
                ExpressionAttributeNames={"#count": "IncidentCount"},
                ExpressionAttributeValues={":zero": 0, ":one": 1, ":limit": MAX_INCIDENTS},
            )
        except Exception as exc:
            if exc.__class__.__name__ == "ConditionalCheckFailedException":
                return _response(
                    429,
                    {"detail": "This free allowance demo has reached 10,000 incidents."},
                )
            raise
        table.put_item(Item=incident, ConditionExpression="attribute_not_exists(PK)")
        return _response(201, {"incident": _public_incident(incident)})

    if method == "GET" and path == "/incidents":
        try:
            limit = int((event.get("queryStringParameters") or {}).get("limit", "20"))
        except ValueError:
            return _response(400, {"detail": "limit must be an integer from 1 to 20."})
        if not 1 <= limit <= MAX_LIST_LIMIT:
            return _response(400, {"detail": "limit must be an integer from 1 to 20."})
        result = table.scan(Limit=limit)
        incidents = [
            _public_incident(item)
            for item in result.get("Items", [])
            if item.get("SK") == "METADATA" and item.get("PK", "").startswith("INCIDENT#")
        ]
        incidents.sort(key=lambda item: item["CreatedAt"], reverse=True)
        return _response(200, {"items": incidents, "count": len(incidents)})

    match = re.fullmatch(r"/incidents/([0-9a-f]{32})", path)
    if match and method == "GET":
        result = table.get_item(Key=_incident_key(match.group(1)), ConsistentRead=True)
        incident = result.get("Item")
        if not incident:
            return _response(404, {"detail": "Incident not found."})
        return _response(200, {"incident": _public_incident(incident)})

    status_match = re.fullmatch(r"/incidents/([0-9a-f]{32})/status", path)
    if status_match and method == "PATCH":
        try:
            body = _body(event)
        except (ValueError, UnicodeDecodeError, json.JSONDecodeError):
            return _response(400, {"detail": "Request body must be a small valid JSON object."})
        new_status = body.get("status")
        expected_status = TRANSITIONS.get(new_status) if isinstance(new_status, str) else None
        if not expected_status:
            return _response(422, {"detail": "Status must advance to INVESTIGATING or RESOLVED."})
        try:
            result = table.update_item(
                Key=_incident_key(status_match.group(1)),
                UpdateExpression="SET #status = :new, UpdatedAt = :updated",
                ConditionExpression="attribute_exists(PK) AND #status = :expected",
                ExpressionAttributeNames={"#status": "Status"},
                ExpressionAttributeValues={
                    ":new": new_status,
                    ":expected": expected_status,
                    ":updated": _now(),
                },
                ReturnValues="ALL_NEW",
            )
        except Exception as exc:
            if exc.__class__.__name__ == "ConditionalCheckFailedException":
                return _response(
                    409,
                    {"detail": "Incident not found or status transition is out of order."},
                )
            raise
        return _response(200, {"incident": _public_incident(result["Attributes"])})

    return _response(404, {"detail": "Route not found."})


def _public_incident(item: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": item["IncidentId"],
        "title": item["Title"],
        "description": item["Description"],
        "severity": item["Severity"],
        "status": item["Status"],
        "created_at": item["CreatedAt"],
        "updated_at": item["UpdatedAt"],
    }
