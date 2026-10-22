import json
from collections import Counter

import pytest

from app.ai import graph, quota
from app.ai.schemas import Plan, Recommendations, RootCause
from app.core.config import settings
from app.core.exceptions import LlmQuotaExhaustedError
from evals import generate, grading, runner
from evals.models import Judgment, Labels
from evals.reporting import fraction, render, review_sample
from evals.run import exclusive, main, validate_history_count
from tests.fake_llm import FAKE_RESPONSES, FakeMessage


class EvaluationLLM:
    def __init__(self):
        self.calls = []
        self.fail_schema = None

    def with_structured_output(self, schema, include_raw=False):
        owner = self

        class Structured:
            def invoke(self, prompt):
                owner.calls.append((schema, prompt))
                if schema is owner.fail_schema:
                    raise RuntimeError("private provider error with a credential")
                answers = {
                    **FAKE_RESPONSES,
                    Labels: Labels(category="dependency", service="orders-db"),
                    Judgment: Judgment(agree=True, reason="The asserted cause matches the key."),
                }
                value = answers[schema]
                if include_raw:
                    return {"parsed": value, "raw": FakeMessage("reason"), "parsing_error": None}
                return value

        return Structured()


@pytest.fixture
def model(monkeypatch):
    fake = EvaluationLLM()
    monkeypatch.setattr(graph, "get_llm", lambda: fake)
    return fake


@pytest.fixture
def case():
    return runner.load_scenarios(generate.SCENARIOS)[0]


def evaluate(case, tmp_path):
    return runner.evaluate(*case, tmp_path, runner.identity())


def test_dataset_contains_fifty_cases_balanced_across_categories():
    scenarios = runner.load_scenarios(generate.SCENARIOS)
    assert len(scenarios) == 50
    assert set(Counter(s.category for s, _ in scenarios).values()) == {10}
    assert len({s.family for s, _ in scenarios}) == 10


def test_retrieval_mode_is_part_of_the_evaluation_identity():
    assert runner.identity("off")["retrieval"] == "off"
    assert runner.identity("on")["retrieval"] == "on"


def test_retrieval_evaluation_requires_fifty_history_embeddings():
    with pytest.raises(SystemExit, match="at least 50"):
        validate_history_count(49)
    validate_history_count(50)


def test_evaluation_restores_history_setting_after_baseline(case, tmp_path, model, monkeypatch):
    monkeypatch.setattr(settings, "incident_history_enabled", True)
    record = runner.evaluate(*case, tmp_path, runner.identity("off"))
    assert record["pipeline"]["state"]["history"] == []
    assert settings.incident_history_enabled is True


def test_committed_fixtures_are_reproducible_from_the_fault_table(tmp_path):
    generate.generate(tmp_path)
    for original in generate.SCENARIOS.iterdir():
        assert (tmp_path / original.name).read_bytes() == original.read_bytes()


def test_investigation_sees_no_answer_key_or_fault_metadata(case, tmp_path, model):
    scenario, path = case
    scenario = scenario.model_copy(update={"root_cause": "ANSWER_CANARY", "fix": "FIX_CANARY"})
    runner.evaluate(scenario, path, tmp_path, runner.identity())
    for schema, prompt in model.calls:
        if schema is not Judgment:
            assert "ANSWER_CANARY" not in prompt
            assert "FIX_CANARY" not in prompt
        if schema in {Plan, RootCause, Recommendations}:
            assert '"family"' not in prompt
            assert '"fault"' not in prompt
    assert "ANSWER_CANARY" in model.calls[-1][1]


def test_real_graph_collects_and_persists_fixture_evidence(case, tmp_path, model):
    row = evaluate(case, tmp_path)
    pipeline = row["pipeline"]
    assert pipeline["completed"] == graph.NODE_ORDER
    assert pipeline["state"]["evidence"]
    assert all(r["request_id"] == "request-01" for r in pipeline["state"]["evidence"])
    assert "Investigation report" in pipeline["state"]["report"]


def test_evaluation_restores_the_production_log_path_on_failure(case, tmp_path, model):
    model.fail_schema = RootCause
    original = settings.dummycommerce_log_path
    with pytest.raises(RuntimeError):
        evaluate(case, tmp_path)
    assert settings.dummycommerce_log_path == original


def test_all_five_calls_are_charged_to_the_existing_budget(case, tmp_path, model):
    evaluate(case, tmp_path)
    assert quota.used_today() == 5
    assert [schema for schema, _ in model.calls] == [
        Plan,
        RootCause,
        Recommendations,
        Labels,
        Judgment,
    ]


def test_cached_evaluation_makes_no_more_provider_calls(case, tmp_path, model):
    first = evaluate(case, tmp_path)
    second = evaluate(case, tmp_path)
    assert first == second
    assert len(model.calls) == 5


def test_evaluator_only_changes_reuse_legacy_investigation_and_grade_caches(
    case, tmp_path, model
):
    scenario, log_path = case
    context = runner.identity()
    first = runner.evaluate(scenario, log_path, tmp_path, context)
    pipeline_key = first["pipeline_key"]
    incident = scenario.incident.model_dump(mode="json")
    logs = log_path.read_text(encoding="utf-8")
    legacy_pipeline_key = runner.digest(
        {"identity": context, "incident": incident, "logs": logs}
    )
    pipeline_path = tmp_path / "pipeline" / f"{pipeline_key}.json"
    legacy_pipeline_path = tmp_path / "pipeline" / f"{legacy_pipeline_key}.json"
    pipeline_record = runner.read(pipeline_path)
    pipeline_record["key"] = legacy_pipeline_key
    runner.save(legacy_pipeline_path, pipeline_record)
    pipeline_path.unlink()

    grader_hash = runner.source_hash(
        [runner.BACKEND / "evals" / "grading.py", runner.BACKEND / "evals" / "models.py"]
    )
    labels_key = runner.digest({"pipeline": pipeline_key, "grader": grader_hash})
    legacy_labels_key = runner.digest(
        {"pipeline": legacy_pipeline_key, "grader": grader_hash}
    )
    (tmp_path / "labels" / f"{labels_key}.json").rename(
        tmp_path / "labels" / f"{legacy_labels_key}.json"
    )

    judge_key = runner.digest({"labels": labels_key, "answer": scenario.answer()})
    legacy_judge_key = runner.digest(
        {"labels": legacy_labels_key, "answer": scenario.answer()}
    )
    (tmp_path / "judgments" / f"{judge_key}.json").rename(
        tmp_path / "judgments" / f"{legacy_judge_key}.json"
    )

    changed_context = {**context, "runner_hash": "new-evaluator-only-hash"}
    second = runner.evaluate(scenario, log_path, tmp_path, changed_context)

    assert second["pipeline_key"] == legacy_pipeline_key
    assert len(model.calls) == 5


def test_answer_correction_only_repeats_the_judge(case, tmp_path, model):
    scenario, path = case
    evaluate(case, tmp_path)
    corrected = scenario.model_copy(update={"root_cause": "corrected answer"})
    runner.evaluate(corrected, path, tmp_path, runner.identity())
    assert [schema for schema, _ in model.calls[5:]] == [Judgment]


def test_changed_model_invalidates_pipeline_cache(case, tmp_path, model, monkeypatch):
    evaluate(case, tmp_path)
    model_setting = {
        "gemini": "gemini_model",
        "anthropic": "anthropic_model",
        "openrouter": "openrouter_model",
    }[settings.llm_provider]
    monkeypatch.setattr(settings, model_setting, "different-pinned-model")
    evaluate(case, tmp_path)
    assert len(model.calls) == 10


def test_changed_evidence_limit_invalidates_pipeline_cache(case, tmp_path, model, monkeypatch):
    evaluate(case, tmp_path)
    monkeypatch.setattr(settings, "evidence_max_records", 1)
    changed = evaluate(case, tmp_path)
    assert len(model.calls) == 10
    assert len(changed["pipeline"]["state"]["evidence"]) == 1


def test_changed_log_content_invalidates_pipeline_cache(case, tmp_path, model):
    evaluate(case, tmp_path)
    scenario, path = case
    changed_path = tmp_path / "changed.jsonl"
    changed_path.write_text(path.read_text() + "\n", encoding="utf-8")
    runner.evaluate(scenario, changed_path, tmp_path, runner.identity())
    assert len(model.calls) == 10


def test_quota_exhaustion_resumes_at_the_first_unfinished_node(case, tmp_path, model, monkeypatch):
    monkeypatch.setattr(settings, "llm_requests_per_day", 1)
    with pytest.raises(LlmQuotaExhaustedError):
        evaluate(case, tmp_path)
    assert [schema for schema, _ in model.calls] == [Plan]
    monkeypatch.setattr(settings, "llm_requests_per_day", 5)
    row = evaluate(case, tmp_path)
    assert row["status"] == "completed"
    assert quota.used_today() == 5
    assert [schema for schema, _ in model.calls].count(Plan) == 1


def test_judge_resumes_without_repeating_investigation_or_extraction(
    case, tmp_path, model, monkeypatch
):
    monkeypatch.setattr(settings, "llm_requests_per_day", 4)
    with pytest.raises(LlmQuotaExhaustedError):
        evaluate(case, tmp_path)
    monkeypatch.setattr(settings, "llm_requests_per_day", 5)
    evaluate(case, tmp_path)
    assert len(model.calls) == 5


def test_zero_budget_leaves_every_scenario_pending(case, tmp_path, model, monkeypatch):
    monkeypatch.setattr(settings, "llm_requests_per_day", 0)
    result = runner.run([case, case], tmp_path)
    assert [r["status"] for r in result["results"]] == ["pending", "pending"]
    assert not model.calls


def test_provider_failure_stops_batch_without_persisting_private_error(case, tmp_path, model):
    model.fail_schema = Plan
    result = runner.run([case, case], tmp_path)
    assert [r["status"] for r in result["results"]] == ["failed", "pending"]
    assert result["stopped"] == "RuntimeError"
    assert "credential" not in json.dumps(result)


def test_blind_extraction_reads_only_the_asserted_cause(model):
    grading.extract_labels({"likely_cause": "database down", "supporting_evidence": ["HIDDEN"]})
    assert "database down" in model.calls[0][1]
    assert "HIDDEN" not in model.calls[0][1]


def test_exact_match_does_not_credit_partial_or_abstaining_labels():
    answer = {"category": "dependency", "service": "orders-db"}
    scores = grading.score(
        Labels(category=None, service="orders"),
        Judgment(agree=False, reason="No conclusion"),
        answer,
    )
    assert scores == {"category": False, "service": False, "agreement": False}


def test_grading_keeps_service_and_category_independent():
    answer = {"category": "dependency", "service": "orders-db"}
    scores = grading.score(
        Labels(category="dependency", service="payments.internal"),
        Judgment(agree=False, reason="Wrong upstream"),
        answer,
    )
    assert scores == {"category": True, "service": False, "agreement": False}


def test_empty_results_have_no_accuracy_percentage(case, tmp_path, model, monkeypatch):
    monkeypatch.setattr(settings, "llm_requests_per_day", 0)
    text = render(runner.run([case], tmp_path))
    assert "N/A (0 graded)" in text
    assert "0.0%" not in text
    assert "PARTIAL" in text
    assert "Not assessable" in text


def test_partial_report_shows_the_completed_denominator(case, tmp_path, model):
    text = render(runner.run([case, case], tmp_path, limit=1))
    assert "1/2 graded" in text
    assert "1/1 (100.0%)" in text
    assert "PARTIAL" in text


def test_calibration_reports_nonmonotonic_results_honestly(case, tmp_path, model):
    result = runner.run([case], tmp_path)
    original = result["results"][0]
    result["results"] = [
        {**original, "confidence": "low", "scores": {**original["scores"], "agreement": True}},
        {**original, "confidence": "medium", "scores": {**original["scores"], "agreement": False}},
        {**original, "confidence": "high", "scores": {**original["scores"], "agreement": False}},
    ]
    result["total"] = 3
    assert "Observed high > medium > low: False" in render(result)


def test_binary_accuracy_uses_the_actual_denominator():
    assert fraction(44, 50) == "44/50 (88.0%)"


def test_manual_sample_is_stable_and_independent_of_scores():
    rows = [
        {"id": f"case-{i:02}", "status": "completed", "scores": {"agreement": False}}
        for i in range(50)
    ]
    expected = [r["id"] for r in review_sample(rows)]
    for row in rows:
        row["scores"]["agreement"] = True
    assert [r["id"] for r in review_sample(list(reversed(rows)))] == expected
    assert len(expected) == 10


def test_evaluator_rejects_a_second_process_using_the_same_cache(tmp_path):
    with exclusive(tmp_path), pytest.raises(RuntimeError, match="already running"):
        with exclusive(tmp_path):
            pytest.fail("Second evaluator entered")
    assert not (tmp_path / "runner.lock").exists()


def test_graph_resume_rejects_unknown_node_names():
    with pytest.raises(ValueError, match="Unknown investigation node"):
        graph.build_graph(start_at="not-a-node")


def test_loader_rejects_answer_metadata_in_logs(tmp_path):
    generate.generate(tmp_path)
    path = tmp_path / "case-01.jsonl"
    path.write_text(json.dumps({"timestamp": "2026-10-01", "fault": "db_connection"}))
    with pytest.raises(ValueError, match="Answer metadata"):
        runner.load_scenarios(tmp_path)


def test_loader_rejects_an_orphan_log_fixture(tmp_path):
    generate.generate(tmp_path)
    (tmp_path / "orphan.jsonl").write_text("{}")
    with pytest.raises(ValueError, match="answer key"):
        runner.load_scenarios(tmp_path)


def test_report_only_never_constructs_a_provider(case, tmp_path, model, monkeypatch, capsys):
    result = runner.run([case], tmp_path / "cache")
    runner.save(tmp_path / "results.json", result)

    def forbidden():
        pytest.fail("Report-only constructed a provider")

    monkeypatch.setattr(graph, "get_llm", forbidden)
    assert main(["--report-only", "--output", str(tmp_path)]) == 0
    assert (tmp_path / "RESULTS.md").is_file()
    assert "Model:" in capsys.readouterr().out


def test_cli_emits_a_partial_report_when_the_budget_runs_out(tmp_path, model, monkeypatch, capsys):
    monkeypatch.setattr(settings, "llm_requests_per_day", 0)
    assert main(["--report", "--output", str(tmp_path), "--cache", str(tmp_path / "cache")]) == 2
    assert "0/50 graded" in capsys.readouterr().out
    assert (
        json.loads((tmp_path / "results.json").read_text())["stopped"] == "LlmQuotaExhaustedError"
    )
