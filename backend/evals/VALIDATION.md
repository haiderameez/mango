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

## Resumed run with the supplied test credential

The credential was applied only to the ignored local `.env`. Authentication succeeded.
The first diagnosis encountered `GoogleAPIError`; resuming completed that investigation
and all three grades. The second investigation also completed, but label extraction
encountered another `GoogleAPIError`. A subsequent resume received a provider rate limit:

```text
Provider asked us to back off. Pausing LLM traffic for 37199s.
Coverage: 1/50 graded, 0 failed, 49 pending.
Stop reason: LlmRateLimitedError.
category: 1/1 (100.0%)
service: 1/1 (100.0%)
agreement: 1/1 (100.0%)
```

`RESULTS.md` and `results.json` now contain this latest real run, including the first
case's report and grading reasons. All three scores describe **one case only**, not the
50-case benchmark. Calibration is unassessable and human judge review is still pending.
The second case's completed graph nodes remain in the local cache for resumption.
No quota counters were reset and no model was changed. The provider's backoff ends at
approximately 12:30 PM on 22 October 2026, Asia/Calcutta; do not retry before that time.
The current cooldown is process-local, so restarting the CLI does not enforce it for you.

Phase 5 is **implemented but not accepted as a completed baseline**. After the provider
backoff expires, resume the same command while the API LLM worker is stopped. Keep the
pinned model and configured budget.

The reported dirty-tree flag is retained honestly: `CONTINUE.md` was already untracked.
Source hashes identify the evaluated implementation independently of unrelated files.
The 50-case live baseline and independent ten-case judge review must finish before
claiming benchmark accuracy or comparing a retrieval lift.
