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

## Phase 1 and 6 — filtered index retest

Measured 22 October 2026 against a new disposable PostgreSQL 17 + pgvector database with
10,000 synthetic incidents and an isolated Redis container. The API ran on the host with
four Uvicorn workers; k6 ran in Docker and sent requests through `host.docker.internal`.
The scripts accept a pre-issued `MANGO_TOKEN`, so setup login time is excluded from endpoint
latency. The investigation worker was not running; submissions measured queue acceptance.

The incident register filters on `status=OPEN&severity=HIGH`, orders by creation time, and
has a composite index on `(status, severity, created_at DESC, id DESC)`. PostgreSQL selected
an index-only scan for the filtered top-50 query, with 0.156 ms execution time in
`EXPLAIN ANALYZE`. At 20 VUs, k6 recorded:

```text
requests: 2,274
rate: 37.88 requests/s (includes the graceful drain interval)
p95: 379.66 ms  (threshold: < 250 ms; failed)
HTTP failures: 0
```

A separate 100-VU run against the smaller seeded dataset completed 3,055 register reads at
99.02 requests/s, with p95 2.38 s and zero HTTP failures. This shows saturation well below
the resume target and does not support 450 requests/s at 95 ms.

With a 500-record ingestion payload and 10 VUs, the endpoint accepted 824 requests (412,000
records) at 27.05 requests/s, with zero HTTP failures and p95 792.36 ms (threshold: < 50 ms;
failed). This is HTTP acceptance into the disposable Redis broker; ingestion workers were
not running, so it does not measure persistence or detection throughput. The broker was
cleared after the run.

Four parallel investigation submissions were accepted with zero HTTP failures. Their
endpoint-only p95 was 408.24 ms (threshold: < 250 ms; failed). These queue entries were left
unprocessed in the disposable environment.
