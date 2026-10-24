"""Measure eight fake-LLM investigations across four Celery worker threads.

Run against a disposable PostgreSQL database whose name ends in ``_test`` and a running
Redis broker: ``python -m scripts.measure_distributed_investigations``.
"""
import threading
import time
from urllib.parse import urlparse
from uuid import uuid4

from sqlalchemy import delete, select

from app.ai import graph
from app.ai.quota import used_today
from app.celery_app import celery_app
from app.core.config import settings
from app.database.session import SessionLocal
from app.models.activity import Activity
from app.models.incident import Incident, SeverityLevel
from app.models.user import User
from app.models.workflow import AgentExecution, RunStatus, WorkflowRun
from app.tasks import run_investigation
from tests.fake_llm import FakeStructuredModel

RUN_COUNT = 8
WORKER_COUNT = 4
POLL_SECONDS = 0.025
TIMEOUT_SECONDS = 120


class CountingFakeLLM:
    """Count the graph's structured requests while returning repository fake responses."""

    def __init__(self):
        self._lock = threading.Lock()
        self.calls = 0

    def with_structured_output(self, schema, include_raw=False):
        return CountingStructuredModel(self, schema, include_raw)


class CountingStructuredModel:
    def __init__(self, llm, schema, include_raw):
        self.llm = llm
        self.schema = schema
        self.include_raw = include_raw

    def invoke(self, prompt):
        with self.llm._lock:
            self.llm.calls += 1
        return FakeStructuredModel(self.schema, self.include_raw).invoke(prompt)


def _assert_disposable_database() -> None:
    database = urlparse(settings.database_url).path.lstrip("/")
    if not database.endswith("_test"):
        raise SystemExit("Refusing to write fixtures: DATABASE_URL database must end in _test.")


def _create_runs() -> list[int]:
    with SessionLocal() as db:
        user = db.execute(select(User).where(User.email == "demo@mango.dev")).scalar_one_or_none()
        if user is None:
            raise SystemExit(
                "Seed the disposable database with `python -m scripts.seed_demo` first."
            )

        run_ids = []
        tag = str(time.time_ns())
        for index in range(RUN_COUNT):
            incident = Incident(
                title=f"Concurrency measurement {tag}-{index}",
                description="Synthetic incident used only for the fake-model worker measurement.",
                severity=SeverityLevel.MEDIUM,
                created_by=user.id,
            )
            db.add(incident)
            db.commit()
            db.refresh(incident)
            run = WorkflowRun(
                incident_id=incident.id,
                triggered_by="phase-4-measurement",
                status=RunStatus.PENDING,
            )
            db.add(run)
            db.commit()
            db.refresh(run)
            run_ids.append(run.id)
        return run_ids


def _remove_fixtures(run_ids: list[int]) -> None:
    with SessionLocal() as db:
        runs = list(db.execute(
            select(WorkflowRun).where(WorkflowRun.id.in_(run_ids))
        ).scalars())
        incident_ids = [run.incident_id for run in runs]
        db.execute(delete(AgentExecution).where(AgentExecution.workflow_run_id.in_(run_ids)))
        db.execute(delete(Activity).where(Activity.incident_id.in_(incident_ids)))
        db.execute(delete(WorkflowRun).where(WorkflowRun.id.in_(run_ids)))
        db.execute(delete(Incident).where(Incident.id.in_(incident_ids)))
        db.commit()


def main() -> None:
    _assert_disposable_database()
    settings.llm_requests_per_day = max(settings.llm_requests_per_day, 100)
    settings.llm_requests_per_minute = max(settings.llm_requests_per_minute, 600)
    settings.incident_history_enabled = False

    fake_llm = CountingFakeLLM()
    graph.get_llm = lambda: fake_llm
    run_ids = _create_runs()
    budget_before = used_today()

    worker = celery_app.Worker(
        hostname=f"phase4-measurement-{uuid4().hex[:8]}",
        loglevel="WARNING",
        pool="threads",
        concurrency=WORKER_COUNT,
        queues=["investigations"],
        without_gossip=True,
        without_heartbeat=True,
        without_mingle=True,
    )
    worker_thread = threading.Thread(
        target=worker.start, name="mango-measurement-worker", daemon=True
    )
    worker_thread.start()

    peak_running = 0
    deadline = time.monotonic() + TIMEOUT_SECONDS
    try:
        worker_ready = False
        ready_deadline = time.monotonic() + TIMEOUT_SECONDS
        while worker_thread.is_alive() and time.monotonic() < ready_deadline:
            if celery_app.control.ping(destination=[worker.hostname], timeout=1):
                worker_ready = True
                break
            time.sleep(POLL_SECONDS)
        if not worker_ready:
            raise SystemExit("The embedded Celery worker did not become ready.")
        for run_id in run_ids:
            run_investigation.apply_async(args=(run_id,), queue="investigations")

        while time.monotonic() < deadline:
            with SessionLocal() as db:
                runs = list(db.execute(
                    select(WorkflowRun).where(WorkflowRun.id.in_(run_ids))
                ).scalars())
            peak_running = max(
                peak_running, sum(run.status == RunStatus.RUNNING for run in runs)
            )
            if len(runs) == RUN_COUNT and all(
                run.status in {RunStatus.COMPLETED, RunStatus.FAILED} for run in runs
            ):
                break
            time.sleep(POLL_SECONDS)
        else:
            raise SystemExit(f"Timed out waiting for the {RUN_COUNT} investigations.")
    finally:
        celery_app.control.broadcast("shutdown", destination=[worker.hostname], reply=False)
        worker_thread.join(timeout=10)
        if worker_thread.is_alive():
            raise SystemExit("The embedded Celery worker did not shut down cleanly.")

    completed = sum(run.status == RunStatus.COMPLETED for run in runs)
    budget_delta = used_today() - budget_before
    if completed != RUN_COUNT:
        raise SystemExit(f"Only {completed}/{RUN_COUNT} investigations completed.")
    if budget_delta != fake_llm.calls:
        raise SystemExit(
            f"Budget charged {budget_delta} requests, fake model invoked {fake_llm.calls}."
        )
    if peak_running < WORKER_COUNT:
        raise SystemExit(
            f"Peak concurrent RUNNING investigations was {peak_running}, expected at least 4."
        )

    _remove_fixtures(run_ids)
    print(
        f"{completed} investigations completed; {fake_llm.calls} fake-model calls; "
        f"budget delta {budget_delta}; peak RUNNING {peak_running}/{WORKER_COUNT} workers."
    )


if __name__ == "__main__":
    main()
