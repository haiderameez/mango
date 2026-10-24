# Phase 5 validation — 22 October 2026 (Asia/Calcutta)

Implementation commit: `9e30fbb1366db71b51ed93a6280fd01e7c9ccb1c`.
Branch: `codex/phase-5-evaluation`.

Executed from `backend/`:

```text
.\.venv\Scripts\python.exe -m ruff check .
All checks passed!

.\.venv\Scripts\python.exe -m pytest -q
199 passed, 2 warnings in 43.84s
```

The two warnings are the existing short-key JWT test and Google SDK deprecation.

Executed from `dummycommerce/`:

```text
D:\mango\backend\.venv\Scripts\python.exe -m pytest -q test_main.py
15 passed in 4.35s
```

Combined: **214 passing tests**, up from the verified 179-test baseline. The added tests
exercise cache reuse/invalidation, answer isolation, real evidence collection, node and
judge resumption, quota accounting, exact scoring, partial reporting, calibration,
fixture reproducibility, the evaluator lock, and six additional executable faults.

Executed from `backend/`, using the configured real provider, not the test fake:

```text
.\.venv\Scripts\python.exe -m evals.run --report
Model: gemini/gemini-3.5-flash
Coverage: 0/50 graded, 1 failed, 49 pending.
Stop reason: GoogleAuthenticationError.
```

The initial result is preserved in commit `bc62c4e`. The installed LangChain
adapter maps HTTP 401 to this exception. A read-only client check confirmed that the
configured key reaches the client; no key was printed or committed. The local budget
counter records one request consumed by this failed attempt. It was not reset.

## Resumed run with one fixed key from a separate project

One supplied key was applied only to the ignored local `.env`; it remained the fixed key
through this run. The configured daily counter was not reset. Resuming the saved second
investigation completed its labels and judgment. A third case's pipeline was checkpointed,
but a later provider API error stopped its grading. The generated report shows:

```text
Coverage: 2/50 graded, 1 failed, 47 pending.
Stop reason: GoogleAPIError.
category: 2/2 (100.0%)
service: 1/2 (50.0%)
agreement: 2/2 (100.0%)
```

`RESULTS.md` and `results.json` now contain the latest actual output and grading reasons.
Scores are based on **two cases only**, not the 50-case benchmark. Calibration is
unassessable, and human judge review is still pending. All three investigation pipelines
are checkpointed locally; case 3 still needs label extraction and a judgment. Mango's daily
counter is at 19/20. No quota counters were reset and no model was changed. A second key
was not used.

Phase 5 is **implemented but not accepted as a completed baseline**. After the provider
backoff expires, resume the same command while the API LLM worker is stopped. Keep the
pinned model and configured budget.

The reported dirty-tree flag is retained honestly: `CONTINUE.md` was already untracked.
Source hashes identify the evaluated implementation independently of unrelated files.
The 50-case live baseline and independent ten-case judge review must finish before
claiming benchmark accuracy or comparing a retrieval lift.
