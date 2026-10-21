"""Replay a JSONL fixture through Mango and report measured incident collapse."""
import argparse
import json
import os
import secrets
import time
import urllib.error
import urllib.request
from pathlib import Path

from app.database.session import SessionLocal
from app.repositories.incident_repository import IncidentRepository
from app.repositories.ingest_repository import IngestRepository

MAX_BATCH = 500


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--fixture", required=True)
    parser.add_argument("--report", action="store_true")
    args = parser.parse_args()
    base_url = os.getenv("MANGO_URL", "http://localhost:8000").rstrip("/")
    ingest_key = os.getenv("MANGO_INGEST_KEY")
    if not ingest_key:
        parser.error("Set MANGO_INGEST_KEY to a key scoped to outage-test.")

    fixture = Path(args.fixture)
    records = [json.loads(line) for line in fixture.read_text(encoding="utf-8").splitlines()
               if line.strip()]
    if len(records) != 10_000:
        parser.error(f"Expected a 10,000-record fixture, got {len(records)}.")

    run_tag = secrets.token_hex(8)
    for row in records:
        row["request_id"] = f"{row.get('request_id') or 'record'}:{run_tag}"
        if row.get("level") == "ERROR":
            row["error_type"] = f"{row.get('error_type', 'Error')}:{run_tag}"

    for offset in range(0, len(records), MAX_BATCH):
        body = "\n".join(json.dumps(row, separators=(",", ":"))
                         for row in records[offset:offset + MAX_BATCH]).encode()
        request = urllib.request.Request(
            f"{base_url}/ingest/logs",
            data=body,
            headers={"X-Ingest-Key": ingest_key, "Content-Type": "application/x-ndjson"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                if response.status != 202:
                    raise RuntimeError(f"Batch was not accepted: HTTP {response.status}")
        except urllib.error.HTTPError as error:
            detail = error.read().decode()
            raise RuntimeError(
                f"Ingestion failed: HTTP {error.code} {detail}"
            ) from error

    deadline = time.monotonic() + 30
    while True:
        with SessionLocal() as db:
            ingested = IngestRepository(db).count_by_service_and_request_tag(
                "outage-test", run_tag
            )
        if ingested == len(records):
            break
        if time.monotonic() >= deadline:
            raise SystemExit(
                f"Only {ingested}/{len(records)} replay records finished ingestion."
            )
        time.sleep(0.1)

    expected_failures = sum(row.get("level") == "ERROR" for row in records)
    deadline = time.monotonic() + 30
    while True:
        with SessionLocal() as db:
            incidents = IncidentRepository(db).get_service_incidents_by_request_tag(
                "outage-test", run_tag
            )
        failures = sum(incident.occurrence_count for incident in incidents)
        if len(incidents) == 6 and failures == expected_failures:
            break
        if time.monotonic() >= deadline:
            raise SystemExit(
                f"Detection finished at {failures}/{expected_failures} failures across "
                f"{len(incidents)}/6 incidents."
            )
        time.sleep(0.1)

    with SessionLocal() as db:
        incidents = IncidentRepository(db).get_service_incidents_by_request_tag(
            "outage-test", run_tag
        )
    failures = sum(incident.occurrence_count for incident in incidents)
    if args.report:
        ratio = failures / len(incidents) if incidents else 0
        print(f"{failures} failures -> {len(incidents)} incidents ({ratio:.1f}:1 collapse)")
        if len(incidents) != 6 or failures != 400:
            raise SystemExit("Replay did not match the fixture's annotated 400 -> 6 result.")


if __name__ == "__main__":
    main()
