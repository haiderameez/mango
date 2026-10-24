"""Render counts and denominators, never silently turn pending cases into accuracy."""

import hashlib


def fraction(correct: int, total: int) -> str:
    return f"{correct}/{total} ({100 * correct / total:.1f}%)" if total else "N/A (0 graded)"


def review_sample(results: list[dict]) -> list[dict]:
    completed = [row for row in results if row["status"] == "completed"]
    return sorted(completed, key=lambda row: hashlib.sha256(row["id"].encode()).hexdigest())[:10]


def render(run: dict) -> str:
    results = run["results"]
    completed = [row for row in results if row["status"] == "completed"]
    count = len(completed)
    failed = sum(row["status"] == "failed" for row in results)
    pending = sum(row["status"] == "pending" for row in results)
    metadata = run["provenance"]
    identity = run["identity"]
    lines = [
        "# Mango evaluation results",
        "",
        f"Status: {'COMPLETE' if count == run['total'] else 'PARTIAL — not a full benchmark'}.",
        f"Model: `{identity['provider']}/{identity['model']}`; retrieval: {identity['retrieval']}.",
        f"Report date (UTC): {metadata['date']}; commit: `{metadata['commit']}`; "
        f"working tree dirty: {metadata['dirty']}.",
        f"Pipeline source hash: `{identity['pipeline_hash']}`.",
        "",
        f"Command (from backend): `{run.get('command', 'python -m evals.run --report')}`.",
        "",
        f"Coverage: **{count}/{run['total']} graded**, {failed} failed, {pending} pending.",
        f"Stop reason: {run['stopped'] or 'none'}.",
        "",
        "| Measure | Completed scenarios only |",
        "|---|---|",
    ]
    for metric in ("category", "service", "agreement"):
        correct = sum(row["scores"][metric] for row in completed)
        lines.append(f"| {metric} | {fraction(correct, count)} |")
    lines += [
        "",
        "Category and service use exact matches after answer-blind LLM label extraction;",
        "they are not independent of extraction quality. Agreement uses a separate LLM judge.",
        "Both use the pinned investigation model; shared model bias remains a limitation.",
        "",
        "## Confidence calibration",
        "",
        "Correctness here means root-cause agreement, not category or service accuracy.",
        "",
        "| Confidence | Agreement |",
        "|---|---|",
    ]
    rates = {}
    for confidence in ("low", "medium", "high"):
        rows = [row for row in completed if row["confidence"] == confidence]
        correct = sum(row["scores"]["agreement"] for row in rows)
        rates[confidence] = correct / len(rows) if rows else None
        lines.append(f"| {confidence} | {fraction(correct, len(rows))} |")
    if any(rate is None for rate in rates.values()):
        calibration = "Not assessable: at least one confidence bin is empty."
    else:
        monotonic = rates["high"] > rates["medium"] > rates["low"]
        calibration = f"Observed high > medium > low: {monotonic}."
    lines += [
        "",
        calibration,
        "Small, correlated fault families limit calibration conclusions.",
        "",
        "## Per-scenario audit",
        "",
        "| Scenario | Status | Confidence | Category | Service | Agreement |",
        "|---|---|---|---|---|---|",
    ]
    for row in results:
        scores = row.get("scores", {})
        lines.append(
            f"| {row['id']} | {row['status']} | {row.get('confidence', '—')} | "
            f"{scores.get('category', '—')} | {scores.get('service', '—')} | "
            f"{scores.get('agreement', '—')} |"
        )
    sample = review_sample(results)
    lines += [
        "",
        "## Manual judge review",
        "",
        "Pending human review. No manual validation is claimed.",
        "Deterministic review sample (hash order, independent of score): "
        + (", ".join(row["id"] for row in sample) or "none available")
        + ".",
        "Review the saved reports, keys and judge reasons in results.json; record independent",
        "agree/disagree decisions and explanations in REVIEW.md before claiming validation.",
        "",
        "## Scope and retrieval lift",
        "",
        "50 synthetic cases: 10 fault families × 5 evidence/noise variants, not 50 independent",
        "production outages. Fixtures come from DummyCommerce's fault table. No training or",
        "prompt tuning on these answers is represented as held-out accuracy.",
        (
            "Retrieval lift: pending a complete paired baseline and retrieval run."
            if identity["retrieval"] == "off"
            else "Retrieval lift: pending a complete paired baseline with retrieval disabled."
        ),
        "Full node outputs, exact evidence, keys, grading reasons and original execution",
        "provenance are in results.json. Cached runs retain their original commit and date.",
        "",
    ]
    return "\n".join(lines)
