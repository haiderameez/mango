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

See `RESULTS.md` and `results.json` for the generated output. The installed LangChain
adapter maps HTTP 401 to this exception. A read-only client check confirmed that the
configured key reaches the client; no key was printed or committed. The local budget
counter records one request consumed by this failed attempt. It was not reset.

No accuracy or calibration percentage is available, and no manual judge review has
occurred. Phase 5 is **implemented but not accepted as a completed baseline**. Update
`GOOGLE_API_KEY` locally in `backend/.env` with a working credential, then resume the same
command while the API LLM worker is stopped. Keep the pinned model and configured budget.

The reported dirty-tree flag is retained honestly: `CONTINUE.md` was already untracked.
Source hashes identify the evaluated implementation independently of unrelated files.
The 50-case live baseline and independent ten-case judge review must finish before
claiming benchmark accuracy or comparing a retrieval lift.
