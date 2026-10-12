"""Run real investigations against real DummyCommerce logs and save what they produced.

    python -m scripts.capture_fixtures                      # all faults
    python -m scripts.capture_fixtures dependency_down      # one of them

Output goes to `scripts/demo_fixtures.json`, which `scripts.seed_demo` replays. That is how
the demo dataset carries genuine agent reasoning and genuine reports without a deployed
instance needing a log file, an API key or a single request.

This spends real LLM budget: three provider calls per fault, paced by the ordinary limiter.
It writes to a throwaway SQLite file, never to the configured database.
"""
# The settings object is built at import time, so the environment has to be arranged first.
import os
import pathlib
import sys

HERE = pathlib.Path(__file__).resolve().parent
WORK = HERE / ".capture"
WORK.mkdir(exist_ok=True)

os.environ["DATABASE_URL"] = f"sqlite:///{(WORK / 'capture.db').as_posix()}"
os.environ["DUMMYCOMMERCE_LOG_PATH"] = str(WORK / "app.jsonl")
os.environ["LOG_PATH"] = str(WORK / "app.jsonl")
# Long enough that the whole emitted sequence is in scope however slowly the run starts.
os.environ.setdefault("EVIDENCE_WINDOW_MINUTES", "60")

sys.path.insert(0, str(HERE.parents[1] / "dummycommerce"))

import argparse  # noqa: E402
import json  # noqa: E402
import logging  # noqa: E402
import time  # noqa: E402
import uuid  # noqa: E402

import main as dummycommerce  # noqa: E402

from app.ai import quota  # noqa: E402
from app.core.config import settings  # noqa: E402
from app.database.base import Base  # noqa: E402
from app.database.session import SessionLocal, engine  # noqa: E402
from app.models import *  # noqa: E402,F403  (registers every table on Base.metadata)
from app.models.incident import Incident, SeverityLevel  # noqa: E402
from app.models.user import User  # noqa: E402
from app.repositories.activity_repository import ActivityRepository  # noqa: E402
from app.repositories.incident_repository import IncidentRepository  # noqa: E402
from app.repositories.workflow_repository import WorkflowRepository  # noqa: E402
from app.services.investigation_service import InvestigationService  # noqa: E402

FIXTURES = HERE / "demo_fixtures.json"
ATTEMPTS = 4
# A free-tier daily quota resets in hours, not minutes. Waiting that out is not worth it:
# say so and let the operator point --model at one with its own allowance.
MAX_COOLDOWN_SECONDS = 300

logging.basicConfig(level="INFO", format="%(asctime)s %(levelname)-7s %(name)s | %(message)s")
logger = logging.getLogger("capture")


def _emit(fault_name: str, fault: dict) -> str:
    """Write the log sequence this fault leaves behind, as DummyCommerce itself writes it."""
    request_id = uuid.uuid4().hex[:12]

    for level, message, extra in fault["events"]:
        dummycommerce.log(
            level,
            message,
            endpoint="POST /orders",
            request_id=request_id,
            fault=fault_name,
            **extra,
        )

    return request_id


def _wait_out_any_cooldown() -> bool:
    """True if we are clear to send. False if the provider wants longer than we will wait."""
    while quota.is_cooling_down():
        pause = quota.cooldown_remaining() + 2

        if pause > MAX_COOLDOWN_SECONDS:
            logger.error(
                "The provider wants %.1f hours before the next request. The free-tier quota "
                "is per model, so try --model with a different one.",
                pause / 3600,
            )
            return False

        logger.info("Provider cooldown: waiting %.0fs", pause)
        time.sleep(pause)

    return True


def capture(fault_names: list[str]) -> list[dict]:
    Base.metadata.create_all(engine)
    db = SessionLocal()

    reporter = db.query(User).filter(User.email == "capture@mango.dev").one_or_none()

    if reporter is None:
        reporter = User(name="DummyCommerce", email="capture@mango.dev", password_hash="unused")
        db.add(reporter)
        db.commit()

    service = InvestigationService(
        WorkflowRepository(db), IncidentRepository(db), ActivityRepository(db)
    )
    captured = []

    for fault_name in fault_names:
        fault = dummycommerce.FAULTS[fault_name]
        request_id = _emit(fault_name, fault)
        failure = fault["events"][-1][1]

        incident = Incident(
            title=fault["title"],
            description=(
                f"POST /orders returned {fault['status']}: {failure} (request_id={request_id})"
            ),
            severity=SeverityLevel[fault["severity"]],
            created_by=reporter.id,
        )
        db.add(incident)
        db.commit()

        detail = None

        # The free tier returns a transient 503 under load and a 429 if we crowd it, so a
        # failed attempt is worth repeating rather than capturing.
        for attempt in range(1, ATTEMPTS + 1):
            if not _wait_out_any_cooldown():
                break

            run = service.start(incident.id, triggered_by="dummycommerce")
            logger.info("%s: attempt %s of %s", fault_name, attempt, ATTEMPTS)
            service.run(run.id)
            detail = service.get_latest_for_incident(incident.id)

            if detail.status.value == "COMPLETED":
                break

            logger.warning("%s: attempt %s failed: %s", fault_name, attempt, detail.error)
            time.sleep(20)

        if detail.status.value != "COMPLETED":
            logger.error("%s: giving up, not captured", fault_name)
            continue

        record = json.loads(detail.model_dump_json())
        record["fault"] = fault_name
        record["description"] = incident.description
        captured.append(record)
        _save([record])
        logger.info("%s: captured, report is %s characters", fault_name, len(detail.report or ""))

    db.close()
    return captured


def _save(records: list[dict]) -> int:
    """Merge records into the fixture file by fault, leaving the others alone."""
    existing = {}

    if FIXTURES.exists():
        existing = {f["fault"]: f for f in json.loads(FIXTURES.read_text(encoding="utf-8"))}

    existing.update({r["fault"]: r for r in records})

    FIXTURES.write_text(
        json.dumps(list(existing.values()), indent=2, ensure_ascii=False), encoding="utf-8"
    )

    return len(existing)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "faults",
        nargs="*",
        default=["dependency_down", "db_connection"],
        choices=sorted(dummycommerce.FAULTS),
        help="which DummyCommerce faults to investigate",
    )
    parser.add_argument(
        "--model",
        help="override GEMINI_MODEL for this capture; the free-tier quota is per model",
    )
    arguments = parser.parse_args()

    if arguments.model:
        settings.gemini_model = arguments.model
        logger.info("Capturing with %s", arguments.model)

    if not capture(arguments.faults):
        raise SystemExit("Nothing was captured; the existing fixtures are unchanged.")

    print(f"{FIXTURES} now holds {_save([])} fixtures")


if __name__ == "__main__":
    main()
