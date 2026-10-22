# Load measurements

## Phase 1 — queued log ingestion

Measured 22 October 2026 against the API and four-process ingestion worker in Docker, with a
disposable PostgreSQL 17 + pgvector database and Redis broker. The k6 client used the
`load/ingest.js` 500-record JSONL payload, 10 VUs, and 30 seconds. The test checked for HTTP
202 responses, HTTP failure rate below 1%, and p95 below 50 ms.

```text
http_reqs: 815 (26.82/s)
records accepted: 407,500
HTTP failures: 0 / 815 (0.00%)
request duration: avg 331.23 ms, min 55.37 ms, max 895.32 ms
p90: 548.68 ms
p95: 632.85 ms  (threshold: < 50 ms; failed)
```

All iterations completed and the API accepted every batch. This measures the HTTP
authenticate-and-enqueue path; it does not measure the time until the worker finishes
persisting and detecting each batch. Phase 1's latency acceptance criterion remains unmet.
