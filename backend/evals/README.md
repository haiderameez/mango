# Investigation benchmark

From `backend/`, install `requirements-dev.txt`, then run:

```powershell
.\.venv\Scripts\python.exe -m evals.run --report
```

The command calls the configured pinned model and uses the shared PostgreSQL daily budget,
Redis pacing, and provider cooldown. Stop the API LLM worker first so the evaluator can use
the remaining daily budget predictably. Do not reset or separate quota state to obtain more
budget.
The evaluator lock prevents two evaluators sharing a cache from running together.

A cold baseline run requires 250 logical requests: 50 × (3 investigation + 1 answer-blind
label extraction + 1 judge). Retrieval adds one embedding request per scenario, for 300
logical requests. SDK retries can add provider attempts under the current production client's
retry policy. No quota increase or model rotation is performed. Resume the same command when
budget is available. Exit 2 means incomplete, not a successful full benchmark. Select the
mode explicitly with `--retrieval off` (baseline) or `--retrieval on` (requires at least 50
resolved-history embeddings in the configured database).
Provider exceptions stop the batch; results store exception classes, not potentially
credential-bearing error text. `--report-only` renders saved results without provider calls.

`RESULTS.md` summarizes `results.json`, which preserves every completed case's incident,
evidence, node outputs, report, grade, reason, answer and execution provenance. `.cache/`
contains atomic checkpoints after each completed node, extraction and judgment. A crash
between receiving a provider response and saving it can require repeating that one call.
Only the evaluator's process temporarily points the collector at a fixture; production
defaults are restored after each case. No model receives tools or raw filesystem access.

Pipeline caches depend on fixture content, incident, pipeline source, evidence configuration,
provider, model and retrieval mode. Evaluator-only code changes do not invalidate completed
investigations. Older cache entries that also included the evaluator source hash remain
reusable when their recorded pipeline identity and inputs match. Grading has a separate source
hash and answer hash. An answer correction reuses the investigation and blind extraction,
then re-judges. Changed pipeline/model/evidence settings require fresh investigations.

## Dataset and scoring

`python -m evals.generate` deterministically regenerates the committed 50 JSONL/YAML pairs.
They are synthetic fixtures from ten executable DummyCommerce faults, each with clean,
background-noise, sparse, distracting-error and outside-window variants. The existing four
faults are included. Category distribution is balanced (10 cases each). Variants within a
family are correlated; this is not evidence of generalization to 50 independent outages.

For a disposable PostgreSQL database with pgvector installed, migrate it first and then seed
the independent synthetic prior cases:

```powershell
$env:DATABASE_URL = 'postgresql://postgres:postgres@localhost:5433/mango_history_eval_test'
python -m alembic upgrade head
python -m scripts.seed_eval_history
python -m scripts.index_resolved_history --limit 50
```

The seeder refuses database names that do not end in `_test` and refuses a non-empty database.
It creates 50 resolved incidents across the same broad fault families, phrased independently
from the benchmark answer files. A fresh database also starts a fresh local quota counter: carry
forward provider calls already made today before indexing or evaluating. Never use a fresh test
database to reset the daily provider budget.

### Resuming the free OpenRouter baseline

The 2026-10-22 partial run uses `nvidia/nemotron-3.5-super-vl:free` and the separate
`nvidia/nemotron-3.5-embed-1b:free` embedding endpoint. These free endpoints may collect inputs
for model improvement; keep this configuration limited to the synthetic evaluation fixtures.
OpenRouter currently caps free models at 50 requests per day and 20 per minute. The evaluator
sets its daily guard to 50 for this configuration and retains Mango's 10 RPM pacing. The local
counter reached 50/50, so resume after its daily reset. In PowerShell, from `backend/`:

```powershell
$env:DATABASE_URL = 'postgresql://postgres:postgres@127.0.0.1:5433/mango_history_eval_test'
$env:OPENROUTER_MODEL = 'nvidia/nemotron-3.5-super-vl:free'
$env:OPENROUTER_EMBEDDING_MODEL = 'nvidia/nemotron-3.5-embed-1b:free'
$env:LLM_REQUESTS_PER_DAY = '50'
$env:LLM_REQUESTS_PER_MINUTE = '10'
$env:LLM_SHOW_THINKING = 'false'
$env:LLM_MAX_RETRIES = '0'
python -m evals.run --report `
  --cache evals/.cache/openrouter-free-2026-10-22 `
  --output evals/openrouter-free-2026-10-22
```

The command resumes saved work and continues the baseline. Do not change the model, prompt,
grading keys or evidence settings between the baseline and retrieval-on run.
Incident titles are neutral. Injection labels, answers, expected categories and fixes are
never passed to the investigation. No production data or credentials are in the fixtures.

Service means the owner of the root fault: e.g. application misconfiguration belongs to
dummycommerce, unavailable payments to payments.internal, and database locks to orders-db.
The baseline schema has no structured category/service fields, so a separate call extracts
them from the asserted cause without the answer key. Null/abstention counts as incorrect.
Exact matching is deterministic; extraction itself is model-dependent. The agreement judge
sees the answer and full report in a separate request and must explain its decision.
The same pinned model judges itself, a source of correlated bias. Freeze this protocol
before comparing retrieval; do not select cases or rewrite keys to improve measured scores.

Calibration reports agreement per confidence bin, including bin sizes. Empty bins make
monotonicity unassessable. Missing or failed cases are never silently scored as successes.
Partial-run percentages describe only the completed subset, not all 50 scenarios.

## Manual check and future retrieval comparison

The report selects ten completed cases by a deterministic hash ordering independent of
their scores. A human reviewer should read the saved report and answer before the judge's
decision, then record their own decision, rationale, disagreements and reviewer/date in
`REVIEW.md`. Until then, manual validation is explicitly pending.

Compare the same frozen scenario hashes, pinned model and grading protocol. Historical
retrieval entries must be separate from evaluation cases, never their copied answer keys.
Keep baseline and retrieval results in separate output and cache directories.
