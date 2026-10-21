"""Sequential graph execution with atomic, content-addressed checkpoints.

Run in a dedicated process while the API's LLM worker is stopped: v1's quota guard
is process-local. Neither an evaluation nor its model needs a database connection.
"""

import hashlib
import json
import subprocess
from datetime import UTC, datetime
from pathlib import Path

import yaml

from app.ai import graph
from app.core.config import settings
from app.core.exceptions import LlmQuotaExhaustedError, LlmRateLimitedError
from evals import grading
from evals.models import Judgment, Labels, Scenario

BACKEND = Path(__file__).resolve().parents[1]


def digest(value) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True).encode()).hexdigest()


def source_hash(paths: list[Path]) -> str:
    return digest(
        {p.relative_to(BACKEND).as_posix(): p.read_text(encoding="utf-8") for p in sorted(paths)}
    )


def identity() -> dict:
    return {
        "provider": settings.llm_provider,
        "model": {
            "gemini": settings.gemini_model,
            "anthropic": settings.anthropic_model,
            "openrouter": settings.openrouter_model,
        }[settings.llm_provider],
        "pipeline_hash": source_hash(
            list((BACKEND / "app" / "ai").glob("*.py"))
            + [BACKEND / "app" / "services" / "evidence.py"]
        ),
        "runner_hash": source_hash([Path(__file__)]),
        "window_minutes": settings.evidence_window_minutes,
        "max_records": settings.evidence_max_records,
        "show_thinking": settings.llm_show_thinking,
        "retrieval": "off",
    }


def provenance() -> dict:
    def git(*args):
        return subprocess.check_output(
            ["git", *args], cwd=BACKEND, text=True, encoding="utf-8"
        ).strip()

    return {
        "commit": git("rev-parse", "HEAD"),
        "dirty": bool(git("status", "--porcelain")),
        "date": datetime.now(UTC).isoformat(),
    }


def load_scenarios(directory: Path) -> list[tuple[Scenario, Path]]:
    result = []
    for path in sorted(directory.glob("*.yaml")):
        scenario = Scenario.model_validate(yaml.safe_load(path.read_text(encoding="utf-8")))
        if scenario.id != path.stem:
            raise ValueError(f"Scenario ID does not match filename: {path.name}")
        log_path = path.with_suffix(".jsonl")
        for line in log_path.read_text(encoding="utf-8").splitlines():
            record = json.loads(line)
            if not isinstance(record, dict) or "timestamp" not in record:
                raise ValueError(f"Invalid log fixture: {log_path.name}")
            if {"fault", "category", "root_cause", "fix"} & record.keys():
                raise ValueError(f"Answer metadata in log fixture: {log_path.name}")
        result.append((scenario, log_path))
    if not result:
        raise ValueError("No scenarios found")
    if {p.stem for p in directory.glob("*.jsonl")} != {s.id for s, _ in result}:
        raise ValueError("Every log fixture must have one answer key")
    return result


def save(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(data, indent=2, sort_keys=True), encoding="utf-8")
    temporary.replace(path)


def read(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}


def evaluate(scenario: Scenario, log_path: Path, cache: Path, context: dict) -> dict:
    incident = scenario.incident.model_dump(mode="json")
    pipeline_key = digest(
        {"identity": context, "incident": incident, "logs": log_path.read_text(encoding="utf-8")}
    )
    path = cache / "pipeline" / f"{pipeline_key}.json"
    record = read(path) or {
        "state": {"incident": incident},
        "completed": [],
        "executions": [],
        "provenance": provenance(),
        "identity": context,
        "key": pipeline_key,
    }
    completed = record["completed"]
    if completed != graph.NODE_ORDER[: len(completed)]:
        raise ValueError("Invalid graph checkpoint order")
    previous_path = settings.dummycommerce_log_path
    try:
        settings.dummycommerce_log_path = str(log_path)
        if len(completed) < len(graph.NODE_ORDER):
            workflow = graph.build_graph(start_at=graph.NODE_ORDER[len(completed)])
            for update in workflow.stream(record["state"], stream_mode="updates"):
                for name, delta in update.items():
                    record["state"].update(delta)
                    completed.append(name)
                    record["executions"].append(
                        {
                            "node": name,
                            "output": delta,
                            "thinking": graph.take_thinking(),
                            "finished_at": datetime.now(UTC).isoformat(),
                        }
                    )
                    save(path, record)
    finally:
        settings.dummycommerce_log_path = previous_path
        graph.take_thinking()

    # Label extraction does not depend on the answer key. Updating an answer must
    # re-judge and re-score, not purchase another investigation or extraction.
    grader_hash = source_hash([BACKEND / "evals" / "grading.py", BACKEND / "evals" / "models.py"])
    labels_key = digest({"pipeline": pipeline_key, "grader": grader_hash})
    labels_path = cache / "labels" / f"{labels_key}.json"
    labels_record = read(labels_path)
    if not labels_record:
        labels = grading.extract_labels(record["state"]["root_cause"])
        graph.take_thinking()
        labels_record = {"labels": labels.model_dump(), "provenance": provenance()}
        save(labels_path, labels_record)
    labels = Labels.model_validate(labels_record["labels"])
    judge_key = digest({"labels": labels_key, "answer": scenario.answer()})
    judge_path = cache / "judgments" / f"{judge_key}.json"
    judge_record = read(judge_path)
    if not judge_record:
        judgment = grading.judge_report(record["state"]["report"], scenario.answer())
        graph.take_thinking()
        judge_record = {"judgment": judgment.model_dump(), "provenance": provenance()}
        save(judge_path, judge_record)
    judgment = Judgment.model_validate(judge_record["judgment"])
    return {
        "id": scenario.id,
        "family": scenario.family,
        "variant": scenario.variant,
        "status": "completed",
        "confidence": record["state"]["root_cause"]["confidence"],
        "scores": grading.score(labels, judgment, scenario.answer()),
        "labels": labels.model_dump(),
        "judgment": judgment.model_dump(),
        "answer": scenario.answer(),
        "pipeline_key": pipeline_key,
        "judge_key": judge_key,
        "pipeline": record,
        "judge_provenance": judge_record["provenance"],
    }


def run(scenarios: list, cache: Path, *, limit: int | None = None) -> dict:
    context = identity()
    results = []
    stopped = None
    for index, (scenario, log_path) in enumerate(scenarios):
        if stopped or (limit is not None and index >= limit):
            results.append({"id": scenario.id, "status": "pending"})
            continue
        try:
            results.append(evaluate(scenario, log_path, cache, context))
        except (LlmQuotaExhaustedError, LlmRateLimitedError) as error:
            stopped = type(error).__name__
            results.append({"id": scenario.id, "status": "pending", "error": stopped})
        except Exception as error:
            # Do not persist arbitrary provider errors: they may contain credentials.
            stopped = type(error).__name__
            results.append({"id": scenario.id, "status": "failed", "error": stopped})
    return {
        "identity": context,
        "provenance": provenance(),
        "results": results,
        "stopped": stopped,
        "total": len(scenarios),
    }
