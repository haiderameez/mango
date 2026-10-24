# Night Window Coffee

A tiny storefront used to demonstrate how a separate application sends live logs to Mango.
The shop writes every order event to a local JSONL file and asynchronously posts the same
sanitized event to Mango's `POST /ingest/logs` endpoint. Mango does not discover or read a
website's logs on its own; the service must ship them, or an agent must be installed to do so.

## Run it against Mango

Run `alembic upgrade head` first. In one terminal, start Mango's API:

```powershell
cd backend
uvicorn app.main:app --reload --port 8000
```

In another terminal, start an ingestion-only worker:

```powershell
cd backend
celery -A app.celery_app:celery_app worker --loglevel=INFO -Q ingestion
```

Then, from the repository root, seed a demo user if the target database has no users and
provision the log source:

```powershell
cd backend
python -m scripts.seed_demo
python -m scripts.provision_night_window_site
```

Keep the printed key private. In another terminal, run the site with that key:

```powershell
cd sample_site
$env:MANGO_URL = "http://localhost:8000"
$env:MANGO_INGEST_KEY = "<key printed by provisioning>"
$env:SERVICE_NAME = "night-window-coffee"
python -m pip install -r requirements.txt
python -m uvicorn main:app --reload --port 8002
```

Open `http://localhost:8002`. A normal order sends one `INFO` event. **Simulate a payment
outage** sends three matching `ERROR` events; after the Mango ingestion worker processes them,
they appear together in one incident. The app does not automatically start an investigation, so
this flow does not spend any model requests. Open the linked Mango console to inspect the
incident and its ingested evidence.

Set `LOG_PATH` to choose a different local JSONL destination. If Mango is offline, local logs
remain on disk; this small example reports delivery failure but does not implement retries or
a durable outbound queue.

Run the app tests from this directory with `python -m pytest -q`; install `requirements-dev.txt`
first if pytest is not already available.
