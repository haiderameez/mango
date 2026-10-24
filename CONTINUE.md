# Continuation prompt

Paste this into a fresh Codex / Claude session opened at the repo root.

---

You are continuing work on **Mango**, an AI-powered incident management platform at this
repo root. Nothing is half-finished: everything described in `MANGO.md` section 3 is
built, tested and committed. Your job is to implement the phases in `MANGO.md` section 4.

## First, read these, in order

1. `MANGO.md` — what Mango is, why it is built this way, what exists, what is left.
2. `plan.md` — the seven phases with schemas, acceptance criteria, and the command that
   measures each one.
3. `README.md` — how to run it.
4. `PRODUCT.md` — product rules the console and API must not contradict.

Then read the code before changing it. Start with `backend/app/ai/graph.py` (the agent
pipeline), `backend/app/services/evidence.py` (log retrieval), and
`backend/app/services/investigation_service.py` (how a run is driven).

## How to run it

```bash
cd backend
./.venv/Scripts/python.exe -m pytest -q      # 179 tests, all green before you start
./.venv/Scripts/python.exe -m ruff check .   # E, F, I, UP, B; line length 100
alembic upgrade head
uvicorn app.main:app --reload                # console at /console
```

Sign in to the seeded demo with `demo@mango.dev` / `mango-demo` after
`python -m scripts.seed_demo`.

## Non-negotiable constraints

- **Layering:** router → service → repository. Routers do HTTP, services do rules,
  repositories do SQL. Graph nodes call services, never the session directly.
- **The model never touches the filesystem or the database.** Evidence collection is
  ordinary tested Python that hands the model a bounded, scrubbed record set. This is the
  product's whole claim; do not let an agent gain tool access to shortcut it.
- **Every LLM call goes through the existing budget guard** in `backend/app/ai/quota.py`.
  The free tier is ~20 requests/day *per model* and the model is pinned deliberately in
  `config.py` — do not switch it to an alias.
- **Every change ships with tests.** Match the existing style: one behaviour per test,
  sentence-shaped names, no mocks where a fake will do (see `tests/fake_llm.py`).
- **Alembic migration for every schema change.** No `create_all` in application code.
- Status is one way: `OPEN` → `INVESTIGATING` → `RESOLVED`. Permissions are per incident,
  not role based, until Phase 7 explicitly adds RBAC.

## Order of work

Build **Phase 5 first** (the evaluation harness) against the current pipeline. It gives a
baseline number immediately, and every later phase can then prove it improved something.
Building the benchmark last is the classic mistake: you end up with no before.

Then Phase 1 → 2 (ingestion and dedup are one story), Phase 3, re-run the benchmark for
the retrieval lift, then Phase 4, Phase 6, Phase 7.

## Working agreement

- One phase per branch, one coherent commit per logical change.
- A phase is done when its acceptance criteria in `plan.md` pass and its measuring command
  has been run. Record the real output in the repo (`evals/RESULTS.md` for Phase 5, the
  k6 output for Phase 6).
- **Never invent a number.** Throughput, latency and the dedup ratio are reproducible from
  a command here. Accuracy is the one figure an interviewer can test by asking what the
  evaluation set was. If the benchmark says 71%, the number is 71%.
- Before you start, tell me which phase you are taking and what you plan to change. After
  each phase, tell me the measured number and update `MANGO.md` section 3 to move that
  work from "left" to "exists".

Start now: read the four files above, run the test suite to confirm a green baseline, then
propose your Phase 5 implementation plan.
