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

## 2026-10-22 history-index preparation

The isolated PostgreSQL 17/pgvector test database `mango_history_eval_test` was migrated to
`f31a9b4c7d2e` and loaded with 50 synthetic resolved incidents (ten fault families, five
paraphrased records each). The seed data is in `history_seed.py`, separate from the benchmark
scenario answer files. All 50 records have completed diagnosis and fix executions; none has an
embedding yet.

`python -m scripts.measure_history_retrieval` returned the expected top match from 50 synthetic
vector fixtures in **27.87 ms**. This verifies the pgvector query path only; it is not a semantic
retrieval result from provider-generated vectors.

`python -m scripts.index_resolved_history --limit 50` was run against that test database. It
stopped before sending an embedding request because the daily guard was conservatively seeded at
20/20 to carry forward today's earlier 20-call benchmark probe. The command reported that the
budget resets in 16.2 hours. The baseline and retrieval-on benchmark modes were not run in this
attempt. No provider requests were made, and the ten-case judge review remains pending until a
complete baseline is available.

## 2026-10-22 configured-model resume check

The current pinned model is `openrouter/qwen/qwen3-30b-a3b-instruct-2507`. A fresh run was
attempted against `mango_history_eval_test`, the migrated pgvector test database, with a separate
cache and output directory so the earlier GPT-4.1 Mini partial results remain intact. The command
reported **0/50 graded**, 0 failed, 50 pending, and stopped with `LlmQuotaExhaustedError` before
the first provider request. The database's persisted daily guard was already 20/20. No quota
counter was reset and no inference call was made. The separate OpenRouter credits check reported
`total_credits: 0`; this is a preflight observation, not a benchmark result.

The run report and empty resumable cache are in `qwen-2026-10-22/` and
`.cache/qwen-2026-10-22/`. Continue this run after the guarded budget resets and usable provider
credit is available. The legacy local `mango` database is not suitable for this checkout: its
Alembic version is `a668ab496681`, which has no migration in the current tree. Do not stamp it;
use the migrated `_test` database for evaluation.

## 2026-10-22 free-model baseline (latest, partial)

To avoid paid credit, the evaluator used the pinned OpenRouter free model
`nvidia/nemotron-3.5-super-vl:free` against synthetic scenarios, with hidden reasoning disabled
to leave room for the required structured JSON under Mango's 2,048-token completion cap. The
model's OpenRouter page documents JSON-schema output support. The evaluation-only daily guard
was set to 50 requests, OpenRouter's current free-model daily cap; Mango pacing remained at 10
requests/minute. The run used the migrated `mango_history_eval_test` database and a fresh cache.

Final command invocation (resuming cached runs; see `openrouter-free-2026-10-22/RESULTS.md` for
the report and `evals/.cache/openrouter-free-2026-10-22/` for checkpoints):

```powershell
$env:DATABASE_URL = 'postgresql://postgres:postgres@127.0.0.1:5433/mango_history_eval_test'
$env:OPENROUTER_MODEL = 'nvidia/nemotron-3.5-super-vl:free'
$env:OPENROUTER_EMBEDDING_MODEL = 'nvidia/nemotron-3.5-embed-1b:free'
$env:LLM_REQUESTS_PER_DAY = '50'
$env:LLM_REQUESTS_PER_MINUTE = '10'
$env:LLM_SHOW_THINKING = 'false'
$env:LLM_MAX_RETRIES = '0'
python -m evals.run --report --limit 4 `
  --cache evals/.cache/openrouter-free-2026-10-22 `
  --output evals/openrouter-free-2026-10-22
```

Coverage: **4/50 graded**, 0 failed, 46 pending. Category was 4/4, service identification 3/4,
and root-cause judge agreement 4/4. This is a small, correlated subset, not a full accuracy or
calibration claim. The persisted request guard reached 50/50. Resume the baseline after the next
daily reset with the same model, settings, output and cache, omitting `--limit 4` to continue all
50 cases.

The separate embedding configuration used `nvidia/nemotron-3.5-embed-1b:free`. OpenRouter returns
2,048 dimensions for that model and documents that vectors can be truncated; Mango stores the
first 768 dimensions to match its existing pgvector schema. The guarded batch command reported
`Indexed 50 resolved incident(s).` A direct pgvector self-match returned the same stored incident
at cosine similarity 1.0. This checks indexing and query wiring only; semantic retrieval quality
is unmeasured. The retrieval-on benchmark still needs a full paired run with the same chat model
and history embedding model. Free-provider calls used synthetic fixtures and synthetic history
only.
