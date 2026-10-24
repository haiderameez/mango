"""Tests for the optional low-volume AWS recurring-free-allowance API."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path
from typing import Any

import pytest

HANDLER_PATH = (
    Path(__file__).resolve().parents[2] / "infrastructure" / "aws" / "free_monthly_handler.py"
)
SPEC = importlib.util.spec_from_file_location("mango_free_monthly_handler", HANDLER_PATH)
assert SPEC and SPEC.loader
handler_module = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(handler_module)
RENDERER_PATH = (
    Path(__file__).resolve().parents[2] / "infrastructure" / "aws" / "render-free-monthly.py"
)
RENDERER_SPEC = importlib.util.spec_from_file_location("mango_free_monthly_renderer", RENDERER_PATH)
assert RENDERER_SPEC and RENDERER_SPEC.loader
renderer_module = importlib.util.module_from_spec(RENDERER_SPEC)
RENDERER_SPEC.loader.exec_module(renderer_module)


class FakeTable:
    def __init__(self) -> None:
        self.items: dict[tuple[str, str], dict[str, Any]] = {}

    def put_item(self, *, Item: dict[str, Any], ConditionExpression: str) -> None:
        assert ConditionExpression == "attribute_not_exists(PK)"
        key = (Item["PK"], Item["SK"])
        if key in self.items:
            raise AssertionError("test fixture generated a duplicate id")
        self.items[key] = Item

    def get_item(self, *, Key: dict[str, str], ConsistentRead: bool) -> dict[str, Any]:
        assert ConsistentRead is True
        item = self.items.get((Key["PK"], Key["SK"]))
        return {"Item": item} if item else {}

    def scan(self, *, Limit: int) -> dict[str, list[dict[str, Any]]]:
        return {"Items": list(self.items.values())[:Limit]}

    def update_item(self, **kwargs: Any) -> dict[str, Any]:
        key = kwargs["Key"]
        item = self.items.get((key["PK"], key["SK"]))
        values = kwargs["ExpressionAttributeValues"]
        if key["PK"] == "SYSTEM":
            current_count = item.get("IncidentCount", 0) if item else 0
            if current_count >= values[":limit"]:
                error_type = type("ConditionalCheckFailedException", (Exception,), {})
                raise error_type("incident demo limit reached")
            self.items[(key["PK"], key["SK"])] = {**key, "IncidentCount": current_count + 1}
            return {"Attributes": self.items[(key["PK"], key["SK"])]}
        if not item or item["Status"] != values[":expected"]:
            error_type = type("ConditionalCheckFailedException", (Exception,), {})
            raise error_type("conditional check failed")
        item["Status"] = values[":new"]
        item["UpdatedAt"] = values[":updated"]
        return {"Attributes": item}


def make_event(
    method: str,
    path: str,
    *,
    body: str | None = None,
    headers: dict[str, str] | None = None,
    query: dict[str, str] | None = None,
) -> dict[str, Any]:
    return {
        "headers": headers if headers is not None else {"authorization": "Bearer " + "a" * 32},
        "body": body,
        "queryStringParameters": query or {},
        "requestContext": {"http": {"method": method, "path": path}},
    }


@pytest.fixture
def table(monkeypatch: pytest.MonkeyPatch) -> FakeTable:
    fake = FakeTable()
    monkeypatch.setenv("MANGO_FREE_API_TOKEN", "a" * 32)
    monkeypatch.setattr(handler_module, "_table", lambda: fake)
    return fake


def test_request_without_the_bearer_token_is_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MANGO_FREE_API_TOKEN", "a" * 32)
    def fail_if_table_is_read() -> None:
        pytest.fail("database should not be read")

    monkeypatch.setattr(handler_module, "_table", fail_if_table_is_read)

    response = handler_module.handler(make_event("GET", "/health", headers={}))

    assert response["statusCode"] == 401


def test_incident_can_be_created_and_retrieved(table: FakeTable) -> None:
    created = handler_module.handler(
        make_event(
            "POST",
            "/incidents",
            body='{"title":"Checkout errors","description":"upstream timeout","severity":"HIGH"}',
        )
    )
    incident = json.loads(created["body"])["incident"]

    assert created["statusCode"] == 201
    assert incident["status"] == "OPEN"
    detail = handler_module.handler(make_event("GET", f"/incidents/{incident['id']}"))
    assert json.loads(detail["body"])["incident"] == incident
    assert len(table.items) == 2


def test_incident_status_moves_forward_once(table: FakeTable) -> None:
    created = handler_module.handler(make_event("POST", "/incidents", body='{"title":"DB errors"}'))
    incident_id = json.loads(created["body"])["incident"]["id"]

    investigating = handler_module.handler(
        make_event("PATCH", f"/incidents/{incident_id}/status", body='{"status":"INVESTIGATING"}')
    )
    resolved = handler_module.handler(
        make_event("PATCH", f"/incidents/{incident_id}/status", body='{"status":"RESOLVED"}')
    )
    reopened = handler_module.handler(
        make_event("PATCH", f"/incidents/{incident_id}/status", body='{"status":"OPEN"}')
    )

    assert json.loads(investigating["body"])["incident"]["status"] == "INVESTIGATING"
    assert json.loads(resolved["body"])["incident"]["status"] == "RESOLVED"
    assert reopened["statusCode"] == 422


def test_create_rejects_invalid_incident_fields(table: FakeTable) -> None:
    response = handler_module.handler(
        make_event("POST", "/incidents", body='{"title":" ","severity":"URGENT"}')
    )

    assert response["statusCode"] == 422
    assert not table.items


def test_list_limit_cannot_exceed_the_bounded_page_size(table: FakeTable) -> None:
    response = handler_module.handler(make_event("GET", "/incidents", query={"limit": "21"}))

    assert response["statusCode"] == 400


def test_incident_storage_stops_at_the_free_profile_limit(table: FakeTable) -> None:
    table.items[("SYSTEM", "INCIDENT_COUNT")] = {
        "PK": "SYSTEM",
        "SK": "INCIDENT_COUNT",
        "IncidentCount": handler_module.MAX_INCIDENTS,
    }

    response = handler_module.handler(make_event("POST", "/incidents", body='{"title":"limit"}'))

    assert response["statusCode"] == 429
    assert len(table.items) == 1


def test_template_renderer_includes_the_deployable_handler(tmp_path: Path) -> None:
    template_path = HANDLER_PATH.parent / "free-monthly.yml"
    output_path = tmp_path / "rendered.yml"

    renderer_module.render(template_path, HANDLER_PATH, output_path)

    rendered = output_path.read_text(encoding="utf-8")
    assert "# Generated by infrastructure/aws/render-free-monthly.py." not in rendered
    assert "def handler(event: dict[str, Any]" in rendered
    assert "raise RuntimeError('Render the Lambda handler" not in rendered
