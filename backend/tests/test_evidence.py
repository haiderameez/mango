import json
from datetime import UTC, datetime, timedelta

import pytest

from app.core.config import settings
from app.services import evidence

NOW = datetime(2026, 10, 12, 12, 0, tzinfo=UTC)


def write_log(path, records):
    path.write_text("\n".join(json.dumps(record) for record in records), encoding="utf-8")
    return str(path)


def record(minutes_ago=1, level="ERROR", message="boom", **extra):
    return {
        "timestamp": (NOW - timedelta(minutes=minutes_ago)).isoformat(),
        "level": level,
        "service": "dummycommerce",
        "message": message,
        **extra,
    }


def test_missing_log_file_yields_no_evidence(tmp_path):
    assert evidence.collect(NOW, log_path=str(tmp_path / "nope.jsonl")) == []


def test_unparseable_lines_are_skipped(tmp_path):
    path = tmp_path / "app.jsonl"
    path.write_text(
        "not json\n" + json.dumps(record()) + "\n\n[1,2,3]\n",
        encoding="utf-8",
    )

    assert len(evidence.collect(NOW, log_path=str(path))) == 1


def test_records_outside_the_window_are_excluded(tmp_path):
    path = write_log(
        tmp_path / "app.jsonl",
        [record(minutes_ago=1, message="inside"), record(minutes_ago=600, message="ancient")],
    )

    messages = [r["message"] for r in evidence.collect(NOW, log_path=path)]

    assert messages == ["inside"]


def test_records_after_the_incident_are_excluded(tmp_path):
    path = write_log(
        tmp_path / "app.jsonl",
        [record(minutes_ago=1, message="before"), record(minutes_ago=-30, message="after")],
    )

    messages = [r["message"] for r in evidence.collect(NOW, log_path=path)]

    assert messages == ["before"]


def test_errors_are_preferred_over_info(tmp_path):
    path = write_log(
        tmp_path / "app.jsonl",
        [record(level="INFO", message="listed products"), record(level="ERROR", message="boom")],
    )

    messages = [r["message"] for r in evidence.collect(NOW, log_path=path)]

    assert messages == ["boom"]


def test_info_only_window_still_returns_evidence(tmp_path):
    path = write_log(tmp_path / "app.jsonl", [record(level="INFO", message="all fine")])

    messages = [r["message"] for r in evidence.collect(NOW, log_path=path)]

    assert messages == ["all fine"]


def test_newest_first(tmp_path):
    path = write_log(
        tmp_path / "app.jsonl",
        [record(minutes_ago=5, message="older"), record(minutes_ago=1, message="newer")],
    )

    messages = [r["message"] for r in evidence.collect(NOW, log_path=path)]

    assert messages == ["newer", "older"]


def test_keyword_narrows_the_selection(tmp_path):
    path = write_log(
        tmp_path / "app.jsonl",
        [
            record(message="connection refused", endpoint="POST /orders"),
            record(message="disk pressure", endpoint="GET /health"),
        ],
    )

    messages = [r["message"] for r in evidence.collect(NOW, keyword="orders", log_path=path)]

    assert messages == ["connection refused"]


def test_keyword_that_matches_nothing_falls_back_to_the_window(tmp_path):
    path = write_log(tmp_path / "app.jsonl", [record(message="connection refused")])

    messages = [r["message"] for r in evidence.collect(NOW, keyword="kubernetes", log_path=path)]

    assert messages == ["connection refused"]


def test_results_are_capped(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "evidence_max_records", 3)
    path = write_log(tmp_path / "app.jsonl", [record(message=f"e{n}") for n in range(20)])

    assert len(evidence.collect(NOW, log_path=path)) == 3


def test_secrets_never_reach_the_evidence(tmp_path):
    path = write_log(
        tmp_path / "app.jsonl",
        [record(password="hunter2", token="abc123", api_key="sk-live-xyz")],
    )

    collected = json.dumps(evidence.collect(NOW, log_path=path))

    assert "hunter2" not in collected
    assert "sk-live-xyz" not in collected


def test_only_known_fields_are_kept(tmp_path):
    path = write_log(
        tmp_path / "app.jsonl",
        [record(endpoint="POST /orders", request_id="abc", error_type="OperationalError", pii="x")],
    )

    collected = evidence.collect(NOW, log_path=path)[0]

    assert collected["endpoint"] == "POST /orders"
    assert collected["request_id"] == "abc"
    assert collected["error_type"] == "OperationalError"
    assert "pii" not in collected


def test_naive_timestamps_are_treated_as_utc(tmp_path):
    path = write_log(
        tmp_path / "app.jsonl",
        [{"timestamp": (NOW - timedelta(minutes=2)).replace(tzinfo=None).isoformat(),
          "level": "ERROR", "message": "naive"}],
    )

    assert [r["message"] for r in evidence.collect(NOW, log_path=path)] == ["naive"]


@pytest.mark.parametrize("timestamp", ["", "yesterday", None])
def test_records_without_a_usable_timestamp_are_dropped(tmp_path, timestamp):
    path = write_log(tmp_path / "app.jsonl", [{"timestamp": timestamp, "message": "x"}])

    assert evidence.collect(NOW, log_path=path) == []


def test_naive_incident_timestamp_is_accepted(tmp_path):
    path = write_log(tmp_path / "app.jsonl", [record(message="boom")])

    assert len(evidence.collect(NOW.replace(tzinfo=None), log_path=path)) == 1
