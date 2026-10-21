# Mango

One file: what this is, why it is built this way, what exists today, what is left.
Phase detail and acceptance criteria live in [plan.md](plan.md); this is the map.

---

## 1. What Mango is

An incident management platform that investigates its own incidents with a multi-agent
AI workflow reading the failing application's real logs.

The loop: an application breaks → an incident exists in Mango → five agents run over the
logs around that incident → an engineer reads a report naming a probable cause, the
evidence behind it, a confidence level, and what to check next.

A companion app, `dummycommerce/`, is a deliberately breakable storefront. It fails on
demand, writes JSONL logs, and files incidents against Mango. It is the test subject that
makes the whole thing demonstrable without a real outage.

## 2. Why it is built this way

**The investigation is evidence-bound, not a chatbot.** Log retrieval is ordinary tested
Python (`app/services/evidence.py`), not a model with filesystem access. The model only
ever sees a bounded, credential-scrubbed set of records. This is the one property a
generic "paste your error into an LLM" tool cannot truthfully claim.

**Every agent run is persisted.** `AgentExecution` stores each agent's output, duration
and reasoning, so any conclusion traces back to what produced it. An unauditable diagnosis
is worthless at 3am.

**The report separates facts from conclusions** and lists evidence that is missing or
contradicting. Confidence tracks evidence quality, demonstrably: the same agents report
`low` on a single log line and `medium` on a correlated failure sequence.

**Layered: router → service → repository.** Routers do HTTP, services do rules,
repositories do SQL. The graph nodes call services, never the database.

**No build step on the frontend.** The console is one static HTML file with vanilla JS,
served by FastAPI at `/console`. The whole product runs with one `uvicorn` command.

**A four-layer budget guard around the LLM**, because the project runs on a free tier:
RPM pacing → a persisted daily request budget → a single-worker FIFO queue → a
provider-driven 429 cooldown. The free tier is roughly 20 requests per day per model, and
aliases silently move between models, so the model is pinned, not aliased.

## 3. What exists today

**Stack:** FastAPI, SQLAlchemy 2, PostgreSQL, Alembic, Pydantic v2, PyJWT, pwdlib/argon2,
LangGraph, LangChain, Gemini. Docker Compose, GitHub Actions CI.

**Tables (6):** `users`, `incidents`, `comments`, `activity`, `workflow_runs`,
`agent_executions`.

**API (21 endpoints):**

- `POST /auth/register`, `POST /auth/login`, `GET /auth/me`
- `POST /incidents`, `GET /incidents`, `GET /incidents/{id}`,
  `PATCH /incidents/{id}`, `PATCH /incidents/{id}/status`,
  `PATCH /incidents/{id}/assign`, `GET /incidents/{id}/activity`
- `POST /incidents/{id}/comments`, `GET /incidents/{id}/comments`,
  `PATCH /comments/{id}`, `DELETE /comments/{id}`
- `POST /incidents/{id}/investigate`, `GET /incidents/{id}/investigation`,
  `GET /incidents/{id}/investigations`, `GET /investigations/{run_id}`,
  `GET /investigations/quota`
- `GET /console`

**The agent pipeline**, a LangGraph `StateGraph`, always in this order:
`planner` → `evidence_collector` → `root_cause` → `fix_recommendation` → `report`.
Two of them (`evidence_collector`, `report`) are plain Python with no model call.
Structured output uses LangChain's `with_structured_output(schema, include_raw=True)`.

**Rules implemented:** severity `LOW|MEDIUM|HIGH|CRITICAL`; status `OPEN` →
`INVESTIGATING` → `RESOLVED`, one way, no skipping. Permissions are per incident, not
role based: only the creator assigns, only creator or assignee changes status, only the
author edits or deletes a comment.

**Incident intake, three paths:** the REST API with a service account (what DummyCommerce
uses), the console by hand, and the seeded demo dataset.

**Console:** incident register with severity and status, incident detail with activity
timeline and comments, and the investigation view showing the five agent route with real
durations, reasoning, and the final report.

**Demo data:** `scripts/seed_demo.py` seeds three users, six incidents across every
severity and status, comments and timelines, then replays two *real* captured
investigations from `scripts/demo_fixtures.json`. The fixtures were produced by
`scripts/capture_fixtures.py` running live against real DummyCommerce logs, so a deployed
demo shows genuine agent output with no log file and no API call.

**Deployment:** Dockerfiles for both services, a three-service compose (postgres, api,
dummycommerce) with named volumes for the two pieces of state that must survive a restart
(the log file and the quota counter), migrations at container start, `$PORT` injection for
managed platforms, and a boot-time validator that refuses a placeholder JWT signing key.

**Evaluation tooling:** `backend/evals/` contains 50 reproducible synthetic scenarios
(10 DummyCommerce fault families × 5 evidence/noise variants), an existing-pipeline runner,
answer-blind category/service extraction with exact-match scoring, a separate root-cause
judge, and confidence calibration. Every model call uses the existing quota guard. Atomic
checkpoints resume completed nodes and grades without paying for them again. Run
`python -m evals.run --report` from `backend/`; measured coverage and results are recorded
in `backend/evals/RESULTS.md`. On 22 October 2026 (India time), the resumed run used one
fixed key from a separate project, with Mango's daily counter unchanged. It graded 2/50
cases: category 2/2, service 1/2, and root-cause agreement 2/2. A later provider API error
stopped the run; 48 cases remain ungraded. This two-case subset is not a full-benchmark
accuracy measurement. Full baseline and human review remain pending;
the harness existing is not an accuracy claim.

**Tests:** 214 (199 backend + 15 DummyCommerce), pytest against in-memory SQLite with `StaticPool`, plus ruff
(E, F, I, UP, B; line length 100). Both run in CI on every push.

### Known limits of the current build

- One API process only. The daily budget counter is a file, so a second worker would
  double-spend it. Phase 4 moves it into Postgres.
- Applications self-report incidents. Mango does not yet read logs continuously or detect
  anything itself. Phase 1.
- Phase 5 tooling exists, but the full 50-case live baseline and manual judge check remain.
  A cold evaluation costs 250 logical calls, including extraction and judging; the 20/day
  guard remains in force. No full-benchmark accuracy or retrieval lift can yet be claimed.

## 4. What is left

Seven phases, in `plan.md` with acceptance criteria and the command that measures each.
Summarised:

| Phase | What | Why it matters |
|---|---|---|
| 1 | **Log ingestion and detection.** `POST /ingest/logs`, a `log_records` table with BRIN+GIN indexes, service ingest keys, and rule-based detection that opens incidents. The evidence collector queries the table instead of a file. | Mango *finds* failures instead of being told about them. |
| 2 | **Dedup and correlation.** A normalised `sha256` fingerprint per failure, partial unique index on open incidents, `occurrence_count`, and cross-service correlation into incident groups. | 400 failures become 6 incidents. The collapse ratio is the best number in the project. |
| 3 | **pgvector RAG over history.** Embeddings of resolved incidents, HNSW index, a new `history` graph node feeding prior diagnoses into the root cause prompt above a similarity floor. | The agents reason from everything already learned, not one incident's logs. |
| 4 | **Celery + Redis, retries, SSE.** Distributed workers, per-node retry with checkpointing, the budget moved to an atomic Postgres `UPDATE`, and live reasoning streamed to the console. | Deletes the one-process limit and the two caveats in the README. |
| 5 | **Complete the live baseline and human review.** The 50-scenario harness, grading, caching and calibration tooling are built (section 3). Run all cases under the existing quota, then independently check ten judge decisions. | Record real accuracy and calibration before changing retrieval. Partial runs are labelled, not extrapolated. |
| 6 | **Observability and load.** OpenTelemetry traces across request → queue → each node, Prometheus metrics, k6 load scripts. | p95 and throughput measured rather than asserted. |
| 7 | **Integrations.** Slack notifications, escalation policies, RBAC. | Reads as an on-call tool, not a ticket tracker. |

**Build order:** 5 (baseline) → 1 → 2 → 3 → re-run 5 for the lift → 4 → 6 → 7.

**One rule for whoever implements this:** throughput, latency and the collapse ratio are
reproducible from a command in this repo. Accuracy is the only figure an interviewer can
test by asking what the evaluation set was. Measure it, never invent it.
