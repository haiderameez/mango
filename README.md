# Mango

Mango is an incident management platform that turns application failures into evidence-backed
investigations. It stores incidents and their history, retrieves bounded and scrubbed logs,
and uses a multi-agent workflow to suggest a likely cause and next checks. Engineers stay in
control: Mango does not change the application or apply fixes.

![Mango incident console](docs/console.png)

## What it does

- Collects incidents from the console, API, or authenticated JSONL log ingestion.
- Detects configured error patterns and rates, then groups repeated failures by fingerprint.
- Tracks comments, assignments, status changes, and an append-only activity timeline.
- Runs a persisted LangGraph investigation with bounded log evidence and similar resolved
  cases from PostgreSQL/pgvector.
- Shows investigation progress and the final report in a static console at `/console`.
- Queues work through Celery and Redis; PostgreSQL enforces the shared daily model budget.
- Supports escalation policies, acknowledgements, Slack webhooks, SNS notifications, and
  `admin`, `responder`, and `viewer` access.

The model receives a bounded, credential-scrubbed record set prepared by ordinary Python. It
has no filesystem or database tools. Every investigation stores its agent outputs so an
engineer can inspect how Mango reached its recommendation.

## Architecture

```text
Application logs -> authenticated ingestion -> Celery ingestion worker
                                              -> PostgreSQL detection and fingerprinting
                                              -> incident

Console / API -> FastAPI -> services -> repositories -> PostgreSQL + pgvector
                                |                           |
                                +-> Celery / Redis           +-> bounded evidence/history
                                         |                               |
                                         +------ LangGraph agents <------+
                                                   |
                                             persisted report
```

The application follows `router → service → repository`: routers handle HTTP, services
enforce rules, and repositories own SQL. See [MANGO.md](MANGO.md) for the full inventory and
[plan.md](plan.md) for phases and acceptance criteria.

## Run locally

You need Docker Desktop and a model provider key only if you want live AI investigations.
Copy the example environment file, set a strong JWT secret, then start the stack:

```powershell
Copy-Item backend/.env.example backend/.env
```

Generate a JWT secret with:

```powershell
python -c "import secrets; print(secrets.token_urlsafe(32))"
```

Put the generated value in `backend/.env` as `JWT_SECRET_KEY`. For AI runs, also configure
the key for the selected provider (`GOOGLE_API_KEY` for Gemini or `OPENROUTER_API_KEY` for
OpenRouter). Then run:

```powershell
docker compose up --build
```

Open the console at [http://localhost:8000/console](http://localhost:8000/console), the API
docs at [http://localhost:8000/docs](http://localhost:8000/docs), DummyCommerce at
[http://localhost:8001/docs](http://localhost:8001/docs), and Jaeger at
[http://localhost:16686](http://localhost:16686).

To seed the demo account and six incidents, run in another terminal:

```powershell
docker compose exec api python -m scripts.seed_demo
```

Sign in with `demo@mango.dev` / `mango-demo`. The seed includes two captured investigation
runs, so the console has useful reports without making model calls. Change demo credentials
before exposing the service beyond your machine.

### Trigger a sample failure

Arm a DummyCommerce fault and submit an order:

```powershell
Invoke-RestMethod -Method Post http://localhost:8001/faults/dependency_down
Invoke-RestMethod -Method Post http://localhost:8001/orders `
  -ContentType 'application/json' -Body '{"product_id":1,"quantity":2}'
```

DummyCommerce writes structured logs and reports the incident to Mango. Mango saves the
incident and queues an investigation. Available faults are defined in
[`dummycommerce/faults.py`](dummycommerce/faults.py).

## API and configuration

All user data endpoints require `Authorization: Bearer <token>`. Log ingestion uses a
service-scoped `X-Ingest-Key`. The main routes are:

| Method | Route | Purpose |
|---|---|---|
| `POST` | `/auth/register`, `/auth/login` | Create an account and receive a token |
| `GET` | `/incidents` | Filter and page through incidents |
| `POST` | `/incidents` | Create an incident |
| `GET` | `/incidents/{id}` | Read an incident and its detail |
| `PATCH` | `/incidents/{id}/status` | Advance `OPEN → INVESTIGATING → RESOLVED` |
| `POST` | `/incidents/{id}/investigate` | Queue an investigation |
| `GET` | `/incidents/{id}/investigation/stream` | Stream completed agent steps over SSE |
| `POST` | `/ingest/logs` | Queue up to 500 JSONL records for detection |
| `GET` | `/investigations/quota` | Check today's model budget and queue depth |
| `GET` | `/console` | Open the operator console |

The interactive schema at `/docs` lists all routes. Environment options and defaults are in
[`backend/.env.example`](backend/.env.example). Mango pins model IDs and stops before the
configured daily request budget is exceeded; review the selected provider's actual limits
before enabling investigations.

## Tests and measurements

Run from `backend/`:

```powershell
python -m pytest -q
python -m ruff check .
```

DummyCommerce tests use the same Python environment:

```powershell
python -m pytest ../dummycommerce -q
```

The outage replay measured **400 failure events → 6 incidents (66.7:1)**. The latest
10-VU ingestion run accepted 824 batches at 27.05 requests/second with no HTTP failures, but
its p95 was 792 ms against a 50 ms target. The AI evaluation has only a small completed
subset; it does not support a 50-scenario accuracy claim or the 89% resume figure. Results,
coverage, and limitations are recorded in [`backend/evals/RESULTS.md`](backend/evals/RESULTS.md)
and [`load/RESULTS.md`](load/RESULTS.md).

## AWS deployment options

The full application needs PostgreSQL/pgvector, Redis, and continuously running API and
worker processes. The original stack in [`infrastructure/aws/README.md`](infrastructure/aws/README.md)
uses ECS/Fargate, RDS, ElastiCache, and a load balancer; these services are not covered by
recurring free monthly allowances.

[`infrastructure/aws/FREE-MONTHLY.md`](infrastructure/aws/FREE-MONTHLY.md) documents a
separate limited API using Lambda and DynamoDB allowances. It supports basic incident create,
list, retrieve, and forward-only status updates. It does **not** run the full Mango console,
log detection, Celery workers, vector retrieval, or AI investigation. Free Tier limits are
shared across the AWS account and region; check current usage before deploying. AWS can bill
paid-plan accounts for usage above an allowance, and the public endpoint cannot guarantee a
hard zero-cost ceiling under arbitrary traffic.

## Project map

- [`MANGO.md`](MANGO.md) — current system and known limits
- [`plan.md`](plan.md) — phases, acceptance criteria, and measuring commands
- [`backend/app/ai/graph.py`](backend/app/ai/graph.py) — investigation graph
- [`backend/app/services/evidence.py`](backend/app/services/evidence.py) — bounded log retrieval
- [`backend/evals/README.md`](backend/evals/README.md) — evaluation setup and methodology
- [`dummycommerce/`](dummycommerce/) — breakable application used for demonstrations
- [`sample_site/`](sample_site/) — second example application that sends its own logs
