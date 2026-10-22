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

## Phase 6 — incident register and investigation submission

Measured 22 October 2026 against the same disposable PostgreSQL 17 + pgvector database in
Docker. The API used a fresh, isolated Redis container. The investigation worker was not
started, so submission requests measured queue acceptance without triggering model calls.

`load/api.js` ran for 30 seconds with 20 VUs after the API was warm:

```text
http_reqs: 1,993 (65.11/s), including the setup login
HTTP failures: 0 / 1,993 (0.00%)
request duration: avg 301.76 ms, min 125.85 ms, max 838.14 ms
p90: 470.66 ms
p95: 536.30 ms  (threshold: < 250 ms; failed)
```

`load/investigation.js` submitted four investigations in parallel:

```text
queued: 4 / 4
http_reqs: 5 (four submissions plus setup login)
HTTP failures: 0 / 5 (0.00%)
request duration: avg 830.17 ms, min 487.15 ms, max 928.90 ms
p95: 927.30 ms  (threshold: < 250 ms; failed)
```

The four queue entries were left unprocessed by design and the disposable Redis/PostgreSQL
test containers were removed after measurement. These results do not support a claim of
450 requests/s or 95 ms p95.
