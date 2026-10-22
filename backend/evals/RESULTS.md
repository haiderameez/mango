# Mango evaluation results

Status: PARTIAL — not a full benchmark.
Model: `openrouter/openai/gpt-4.1-mini`; retrieval: off.
Report date (UTC): 2026-10-22T11:30:28.328973+00:00; commit: `35aaee7bdd60d458c60eadbe12534446fab6bd52`; working tree dirty: True.
Pipeline source hash: `855a02cf1f0cd46a6f155864b44df8dd38dd9a7eed99281a40895c028970b5fe`.

Command (from backend): `python -m evals.run --report --limit 4 --cache 'evals\.cache\openrouter' --output 'evals\openrouter-2026-10-22'`.

Coverage: **4/50 graded**, 0 failed, 46 pending.
Stop reason: none.

Quota note: the four OpenRouter scenarios were evaluated with 20 calls against an isolated
test-database counter that began at zero. This does not verify the production shared budget.

| Measure | Completed scenarios only |
|---|---|
| category | 4/4 (100.0%) |
| service | 1/4 (25.0%) |
| agreement | 4/4 (100.0%) |

Category and service use exact matches after answer-blind LLM label extraction;
they are not independent of extraction quality. Agreement uses a separate LLM judge.
Both use the pinned investigation model; shared model bias remains a limitation.

## Confidence calibration

Correctness here means root-cause agreement, not category or service accuracy.

| Confidence | Agreement |
|---|---|
| low | N/A (0 graded) |
| medium | N/A (0 graded) |
| high | 4/4 (100.0%) |

Not assessable: at least one confidence bin is empty.
Small, correlated fault families limit calibration conclusions.

## Per-scenario audit

| Scenario | Status | Confidence | Category | Service | Agreement |
|---|---|---|---|---|---|
| case-01 | completed | high | True | True | True |
| case-02 | completed | high | True | False | True |
| case-03 | completed | high | True | False | True |
| case-04 | completed | high | True | False | True |
| case-05 | pending | — | — | — | — |
| case-06 | pending | — | — | — | — |
| case-07 | pending | — | — | — | — |
| case-08 | pending | — | — | — | — |
| case-09 | pending | — | — | — | — |
| case-10 | pending | — | — | — | — |
| case-11 | pending | — | — | — | — |
| case-12 | pending | — | — | — | — |
| case-13 | pending | — | — | — | — |
| case-14 | pending | — | — | — | — |
| case-15 | pending | — | — | — | — |
| case-16 | pending | — | — | — | — |
| case-17 | pending | — | — | — | — |
| case-18 | pending | — | — | — | — |
| case-19 | pending | — | — | — | — |
| case-20 | pending | — | — | — | — |
| case-21 | pending | — | — | — | — |
| case-22 | pending | — | — | — | — |
| case-23 | pending | — | — | — | — |
| case-24 | pending | — | — | — | — |
| case-25 | pending | — | — | — | — |
| case-26 | pending | — | — | — | — |
| case-27 | pending | — | — | — | — |
| case-28 | pending | — | — | — | — |
| case-29 | pending | — | — | — | — |
| case-30 | pending | — | — | — | — |
| case-31 | pending | — | — | — | — |
| case-32 | pending | — | — | — | — |
| case-33 | pending | — | — | — | — |
| case-34 | pending | — | — | — | — |
| case-35 | pending | — | — | — | — |
| case-36 | pending | — | — | — | — |
| case-37 | pending | — | — | — | — |
| case-38 | pending | — | — | — | — |
| case-39 | pending | — | — | — | — |
| case-40 | pending | — | — | — | — |
| case-41 | pending | — | — | — | — |
| case-42 | pending | — | — | — | — |
| case-43 | pending | — | — | — | — |
| case-44 | pending | — | — | — | — |
| case-45 | pending | — | — | — | — |
| case-46 | pending | — | — | — | — |
| case-47 | pending | — | — | — | — |
| case-48 | pending | — | — | — | — |
| case-49 | pending | — | — | — | — |
| case-50 | pending | — | — | — | — |

## Manual judge review

Pending human review. No manual validation is claimed.
Deterministic review sample (hash order, independent of score): case-01, case-03, case-02, case-04.
Review the saved reports, keys and judge reasons in results.json; record independent
agree/disagree decisions and explanations in REVIEW.md before claiming validation.

## Scope and retrieval lift

50 synthetic cases: 10 fault families × 5 evidence/noise variants, not 50 independent
production outages. Fixtures come from DummyCommerce's fault table. No training or
prompt tuning on these answers is represented as held-out accuracy.
Retrieval lift: pending a complete paired baseline and retrieval run.
Full node outputs, exact evidence, keys, grading reasons and original execution
provenance are in results.json. Cached runs retain their original commit and date.
