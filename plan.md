# Mango — v2 plan

The resume entry at the bottom is written **for the finished system**, not the current one.
Every claim in it maps to a phase here, and every number has a command that measures it.
Ship the phase, run the command, put the real figure in. Nothing goes on the resume before
its phase is merged and its number is measured.

Current state (true today): 21 REST endpoints, 6 tables, 5-agent LangGraph pipeline,
179 tests, single-process queue, apps self-report incidents.

---

## Why the current numbers read weak

"21 endpoints, 6 tables" describes **size**, and size is not an achievement — a CRUD app has
tables too. The numbers that land describe **a hard problem solved under constraint**:
throughput, accuracy against a benchmark, latency under load, noise collapsed, cost per unit
of work. Every phase below exists to produce one of those.

---

## Phase 1 — Log ingestion and automatic detection

Today an application has to file its own incident. Mango should *find* the failure.

**Build**

- `POST /ingest/logs` — accepts a batch of up to 500 JSONL records, `Content-Encoding: gzip`
  supported, authenticated with a per-service ingest key (new `service_keys` table, hashed
  like passwords). Returns 202 immediately; parsing happens off the request path.
- `log_records` table: `id, service, level, message, context JSONB, request_id, ts`, with a
  BRIN index on `ts` and a GIN index on `context`. BRIN because this table is append-only
  and time-ordered — it is ~1/30th the size of a B-tree here.
- A detector that runs on each batch: an incident opens when a rule fires. Start with three
  rules in a `detection_rules` table (`service`, `level`, `threshold`, `window_seconds`,
  `pattern`), e.g. *5 ERROR records from one service in 60s*, *any record matching
  `CRITICAL|OutOfMemory`*, *error rate above 5% of that service's last 5 minutes*.
- The evidence collector switches from reading a file to querying `log_records`. Its
  signature stays `collect(incident_created_at, keyword, ...)` — that interface was built for
  exactly this swap.

**Acceptance**

- Replaying a 10k-record fixture through `/ingest/logs` opens exactly the incidents the
  fixture is annotated to produce — no more, no fewer.
- Ingest endpoint stays under 50ms p95 with a 500-record batch (it only enqueues).

**Unlocks:** ingestion throughput, and "detects" instead of "receives".

**Measure**
```bash
k6 run load/ingest.js          # records/sec sustained, p95 latency
```

---

## Phase 2 — Deduplication and correlation

One outage produces hundreds of identical failures. A platform that opens 300 incidents for
one broken database is worse than useless at 3am.

**Build**

- A **fingerprint** per failure: `sha256(service + normalised_message + error_type)`, where
  normalisation strips numbers, UUIDs, IPs and timestamps so
  `connection to 10.0.3.17:5432 failed` and `connection to 10.0.4.2:5432 failed` collapse to
  one fingerprint. Store it on `incidents`, uniquely indexed with a partial index
  `WHERE status != 'RESOLVED'`.
- Re-occurrence bumps `occurrence_count` and `last_seen_at` on the open incident instead of
  creating a new one. The activity timeline records the burst, not each hit.
- **Correlation**: incidents from different services within a 5-minute window that share a
  `request_id` or an upstream name link into an `incident_group`, so a cascade reads as one
  event with a probable origin rather than four unrelated pages.

**Acceptance**

- The 10k-record fixture, which contains 400 failures from 6 root faults, produces 6
  incidents with occurrence counts summing to 400.

**Unlocks:** the noise-collapse ratio — the single most quotable number in the project.

**Measure**
```bash
python -m scripts.replay --fixture load/outage.jsonl --report
# prints: 400 failures -> 6 incidents (66:1 collapse)
```

---

## Phase 3 — Retrieval over incident history (pgvector)

The agents currently reason from one incident's logs. They should reason from everything the
organisation has already learned.

**Build**

- `pgvector` extension; `incident_embeddings` table holding a 768-dim embedding of
  `title + description + root cause + resolution` per resolved incident, generated with the
  pinned `openai/text-embedding-3-small` model through OpenRouter. Embedding calls share Mango's
  atomic daily request budget and Redis model pacing with chat calls.
- An HNSW index (`vector_cosine_ops`, `m=16`, `ef_construction=64`) — not IVFFlat, which
  needs training data this table will not have for months.
- A new graph node, **`history`**, between `evidence_collector` and `root_cause`: fetches the
  3 nearest resolved incidents above a 0.75 similarity floor and passes their diagnoses and
  fixes into the root-cause prompt as prior art. Below the floor it passes nothing — a bad
  neighbour is worse than no neighbour.
- Surface it in the console: *"3 similar incidents, last resolved 11 days ago"* with links.
  This is the feature that makes someone watching a demo sit up.
- Resolving an incident queues best-effort indexing after the incident is committed. A batched
  backfill command indexes older resolved investigations without one request per incident.

**Acceptance**

- With a seeded history of 50 resolved incidents, a repeat of a known fault must retrieve its
  own prior incident as the top match. Verify database retrieval independently with
  `python -m scripts.measure_history_retrieval` against a disposable `*_test` database; verify
  semantic retrieval with provider-generated vectors when the OpenRouter embedding budget is
  available.
- The vector lookup adds under 100ms; measure query/index latency separately from the remote
  embedding request.

**Unlocks:** "RAG over incident history", and a measurable accuracy lift in Phase 5.

---

## Phase 4 — Distributed execution and live streaming

The in-process queue is the honest weak point: one worker, dies on deploy, cannot scale out.

**Build**

- **Celery + Redis**. `InvestigationQueue` becomes a Celery task; the interface the service
  calls does not change. Workers run as their own container.
- **Per-node retry**: each graph node gets `max_retries=2` with exponential backoff, so a
  transient 503 on `fix_recommendation` no longer throws away the 90 seconds already spent on
  planning and root cause. Checkpoint state after each node so a retry resumes mid-graph.
- **The budget moves into Postgres** — a single row per day updated with
  `UPDATE ... SET used = used + 1 WHERE used + 1 <= limit RETURNING used`, which is atomic
  across every worker. The file-based counter cannot survive more than one process, and
  that limitation is currently in the README.
- **Live reasoning over SSE**: `GET /incidents/{id}/investigation/stream` pushes each node's
  start, finish and reasoning as it happens; the console's agent route fills in live instead
  of polling every 2 seconds.

**Acceptance**

- 8 concurrent investigations across 4 workers, zero budget overruns, verified by a test that
  runs them against a fake LLM and asserts the counter equals exactly the calls made.
- Killing a worker mid-run leaves the run resumable, not FAILED.

**Measure**
```bash
python -m scripts.measure_distributed_investigations
# Requires a seeded disposable PostgreSQL database ending in _test and a Redis broker.
# The fake model makes no provider requests; the harness checks eight runs, four-way
# concurrency, and equality between fake calls and the PostgreSQL budget increment.
python -m scripts.measure_worker_recovery
# Requires Docker, a seeded _test PostgreSQL container, and MANGO_TEST_POSTGRES_CONTAINER.
# The harness kills a prefork child during a fake root-cause call and checks redelivery/resume.
```

**Unlocks:** concurrency figures, and deletes two of the three caveats in the README.

---

## Phase 5 — The evaluation harness (the accuracy number)

This is the most important phase on the list. Right now the project cannot claim accuracy,
because nothing measures it. A benchmark turns "the AI works" into a number you can defend.

**Build**

- `evals/scenarios/` — **50 fault scenarios**, each a JSONL log fixture plus a YAML answer
  key: the true root cause, the service at fault, the category
  (`dependency`, `resource_exhaustion`, `code_defect`, `config`, `latency`), and the fix that
  actually resolved it. Generate them by extending DummyCommerce's fault table; each existing
  fault becomes a family with varied log noise around the same cause.
- A grader: run the pipeline over every scenario, then score with three measures —
  **category accuracy** (exact match, deterministic), **service identification** (exact
  match), and **root-cause agreement** (an LLM judge given the answer key and the report,
  returning agree/disagree with a reason; sample 10 by hand to confirm the judge is sane).
- **Calibration**, which is the genuinely interesting metric: group results by the confidence
  the agents reported and check that `high` is right more often than `medium`, and `medium`
  more often than `low`. A model that knows when it does not know is the product's whole
  claim, and almost nobody measures it.
- Run it with and without Phase 3 retrieval to get the lift.
- Budget: 50 scenarios × 3 calls = 150 requests, well past a free-tier day. Run it in
  batches across models, or spend ~$2 of paid credit. Cache results per scenario hash so a
  rerun only re-grades what changed.

**Acceptance**

- `python -m evals.run --report` emits a markdown table, committed to `evals/RESULTS.md`
  with the model, date and commit.

**Unlocks:** the accuracy percentage, the calibration claim, and the retrieval lift. **Use
whatever number comes out.** If it is 71%, write 71% — a defended 71% beats an invented 94%,
and the follow-up question is always "how did you measure that?"

---

## Phase 6 — Observability and load

**Build**

- **OpenTelemetry** traces across request → queue → each agent node, exported to Jaeger in
  compose. One trace showing a 150-second investigation broken into five spans is the best
  screenshot in the project after the console.
- **Prometheus** metrics at `/metrics`: investigation duration histogram, provider calls,
  budget remaining, queue depth, ingest rate, detection rule firings.
- **k6** scripts in `load/`: ingest throughput, register read path, investigation submission.
  Run against the compose stack with Postgres tuned to defaults so the figures are honest.
- Fix what the load test finds. The register query with eager-loaded users is the first
  suspect; add a composite index on `(status, severity, created_at DESC)`.

**Unlocks:** p95 latency and sustained throughput, both measured rather than asserted.

**Measure**
```bash
k6 run load/ingest.js && k6 run load/api.js   # p95, p99, rps
```

---

## Phase 7 — Integrations (optional, high demo value, low difficulty)

- **Slack**: incident opened / investigation completed posts to a channel with the probable
  cause and a link. Incoming webhook, about 40 lines.
- **PagerDuty-style escalation**: `escalation_policies` — if a CRITICAL incident is
  unacknowledged for 10 minutes, notify the next person. This is the feature that makes it
  read as an on-call tool rather than a ticket tracker.
- **RBAC**: `admin` / `responder` / `viewer` on top of the existing per-incident rules.

---

## Order to build

1. **Phase 5 first, with the current pipeline.** You get a baseline number immediately, and
   every later phase can then prove it improved something. Building the benchmark last is the
   classic mistake — you end up with no before.
2. Phase 1 → 2 (ingestion and dedup are one story and the dedup ratio is the best number).
3. Phase 3 (retrieval), then re-run the benchmark for the lift.
4. Phase 4 (distributed), then Phase 6 (measure it).
5. Phase 7 if time remains before applications go out.

Phases 1, 2 and 5 alone carry the resume entry. Everything after is upside.

---

## The resume entry this earns

Placeholders in `<<angle brackets>>` are the numbers the phases produce. **Do not ship this
until each one is replaced by a measured value.**

```latex
\resumeProjectHeading
    {\textbf{Mango} $|$ \emph{FastAPI, PostgreSQL, pgvector, LangGraph, LangChain, Celery, Redis, Docker}}{}
    \resumeItemListStart
      \resumeItem{Architected an \textbf{AI-driven incident platform} ingesting \textbf{<<N>>k log events/min}, auto-detecting failures and fingerprinting them into incidents — collapsing \textbf{<<66>>:1 alert noise} across a simulated outage}
      \resumeItem{Engineered a \textbf{multi-agent LangGraph pipeline} with \textbf{LangChain} structured output and \textbf{pgvector RAG} over resolved-incident history, reaching \textbf{<<N>>\% root-cause accuracy} on a \textbf{50-scenario benchmark} — a \textbf{<<N>> pt} lift over the non-retrieval baseline}
      \resumeItem{Scaled to \textbf{<<8>> concurrent investigations} on \textbf{Celery/Redis} workers with per-node retry and an atomic Postgres request budget, sustaining \textbf{p95 <<N>>ms} at \textbf{<<N>> rps} under k6}
      \resumeItem{Instrumented end-to-end with \textbf{OpenTelemetry} and \textbf{Prometheus}; \textbf{<<N>}+ tests, GitHub Actions CI, Docker Compose deployment}
    \resumeItemListEnd
```

Three-bullet cut, if space is tight: merge 4 into 3 and keep the first two intact. The
accuracy bullet is the one that gets you the interview; the dedup ratio is the one they
remember.

### One claim to never invent

Accuracy. It is the only number here an interviewer can test by asking "what was your
evaluation set, and what did the model get wrong?" Everything else — throughput, latency,
collapse ratio — is reproducible from a command in this repo. Keep it that way.
