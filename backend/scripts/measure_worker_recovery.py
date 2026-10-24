"""Kill a prefork Celery child during root-cause analysis and verify resume on redelivery.

Run against a seeded disposable PostgreSQL database whose name ends in ``_test``. Docker
must be available. The harness creates its own isolated Redis broker and removes its test
incident, worker, Redis container, and network when finished.
"""
import os
import socket
import subprocess
import time
from uuid import uuid4

import redis
from sqlalchemy import delete, select
from sqlalchemy.engine import make_url

from app.ai.quota import used_today
from app.celery_app import celery_app
from app.core.config import settings
from app.database.session import SessionLocal
from app.models.activity import Activity
from app.models.incident import Incident, SeverityLevel
from app.models.user import User
from app.models.workflow import AgentExecution, RunStatus, WorkflowRun
from app.tasks import run_investigation

IMAGE = "mango-worker-recovery-test"
WAIT_SECONDS = 120
ROOT_CAUSE_STARTED = "mango:worker-loss:root-cause-started"
ROOT_CAUSE_PID = "mango:worker-loss:root-cause-pid"
ROOT_CAUSE_ATTEMPTS = "mango:worker-loss:root-cause-attempts"
FAKE_CALLS = "mango:worker-loss:fake-calls"


def _docker(*args: str, capture: bool = True) -> str:
    if not capture:
        subprocess.run(["docker", *args], check=True)
        return ""
    result = subprocess.run(
        ["docker", *args], check=True, capture_output=True, text=True
    )
    return result.stdout.strip()


def _create_run() -> tuple[int, int]:
    with SessionLocal() as db:
        user = db.execute(select(User).where(User.email == "demo@mango.dev")).scalar_one_or_none()
        if user is None:
            raise SystemExit("Seed the disposable database with `python -m scripts.seed_demo`.")
        incident = Incident(
            title=f"Worker loss probe {uuid4().hex}",
            description="Synthetic incident for the Celery child-loss recovery measurement.",
            severity=SeverityLevel.MEDIUM,
            created_by=user.id,
        )
        db.add(incident)
        db.commit()
        db.refresh(incident)
        run = WorkflowRun(
            incident_id=incident.id,
            triggered_by="phase-4-worker-loss-measurement",
            status=RunStatus.PENDING,
        )
        db.add(run)
        db.commit()
        db.refresh(run)
        return incident.id, run.id


def _remove_fixture(incident_id: int, run_id: int) -> None:
    with SessionLocal() as db:
        db.execute(delete(AgentExecution).where(AgentExecution.workflow_run_id == run_id))
        db.execute(delete(Activity).where(Activity.incident_id == incident_id))
        db.execute(delete(WorkflowRun).where(WorkflowRun.id == run_id))
        db.execute(delete(Incident).where(Incident.id == incident_id))
        db.commit()


def main() -> None:
    database = make_url(settings.database_url)
    if not (database.database or "").endswith("_test"):
        raise SystemExit("Refusing to write fixtures: DATABASE_URL database must end in _test.")

    suffix = uuid4().hex[:8]
    network = f"mango-worker-loss-{suffix}"
    broker_name = f"mango-worker-loss-redis-{suffix}"
    worker_name = f"mango-worker-loss-worker-{suffix}"
    postgres_container = os.getenv("MANGO_TEST_POSTGRES_CONTAINER")
    with socket.socket() as port_probe:
        port_probe.bind(("127.0.0.1", 0))
        broker_port = port_probe.getsockname()[1]
    host_broker = f"redis://127.0.0.1:{broker_port}/0"
    worker_broker = f"redis://{broker_name}:6379/0"
    test_client = redis.Redis.from_url(host_broker, decode_responses=True)
    incident_id = run_id = None
    worker_started = False

    try:
        _docker("network", "create", network)
        if postgres_container:
            _docker("network", "connect", network, postgres_container)
        _docker(
            "run", "-d", "--name", broker_name, "--network", network,
            "-p", f"127.0.0.1:{broker_port}:6379", "redis:7-alpine",
        )
        deadline = time.monotonic() + 20
        while time.monotonic() < deadline:
            try:
                test_client.ping()
                break
            except redis.RedisError:
                time.sleep(0.2)
        else:
            raise SystemExit("The isolated Redis broker did not become ready.")

        settings.redis_url = host_broker
        celery_app.conf.update(broker_url=host_broker, result_backend=host_broker)
        from app.ai import quota

        quota._redis = test_client
        test_client.delete(ROOT_CAUSE_STARTED, ROOT_CAUSE_PID, ROOT_CAUSE_ATTEMPTS, FAKE_CALLS)

        incident_id, run_id = _create_run()
        budget_before = used_today()
        _docker(
            "build", "-t", IMAGE, "-f", "Dockerfile", ".", capture=False
        )
        worker_database = (
            database.set(host=postgres_container, port=5432)
            if postgres_container
            else database.set(host="host.docker.internal")
        )
        _docker(
            "run", "-d", "--rm", "--name", worker_name, "--network", network,
            "-e", f"DATABASE_URL={worker_database.render_as_string(hide_password=False)}",
            "-e", f"REDIS_URL={worker_broker}",
            "-e", "JWT_SECRET_KEY=phase4-worker-loss-test-secret-0000000000000000",
            "-e", "LLM_PROVIDER=gemini",
            "-e", "LLM_REQUESTS_PER_DAY=100",
            "-e", "LLM_REQUESTS_PER_MINUTE=600",
            "-e", "INCIDENT_HISTORY_ENABLED=false",
            IMAGE, "celery", "-A", "app.celery_app:celery_app", "worker",
            "--loglevel=WARNING", "--pool=prefork", "--concurrency=1",
            "-Q", "investigations", "--include", "scripts.worker_loss_fake_model",
            "--hostname=phase4-loss",
        )
        worker_started = True

        ready_deadline = time.monotonic() + WAIT_SECONDS
        while time.monotonic() < ready_deadline:
            if celery_app.control.ping(timeout=1):
                break
            time.sleep(0.2)
        else:
            raise SystemExit("The prefork Celery worker did not become ready.")

        run_investigation.apply_async(args=(run_id,), queue="investigations")
        blocked_deadline = time.monotonic() + WAIT_SECONDS
        while time.monotonic() < blocked_deadline:
            pid = test_client.get(ROOT_CAUSE_PID)
            if pid:
                break
            time.sleep(0.05)
        else:
            raise SystemExit("The worker did not reach the fake root-cause pause.")

        with SessionLocal() as db:
            planner_saved = db.execute(
                select(AgentExecution.id).where(
                    AgentExecution.workflow_run_id == run_id,
                    AgentExecution.agent_name == "planner",
                    AgentExecution.status == RunStatus.COMPLETED,
                )
            ).scalar_one_or_none()
        if planner_saved is None:
            raise SystemExit("The planner checkpoint was not committed before worker loss.")

        _docker(
            "exec", worker_name, "python", "-c",
            f"import os, signal; os.kill({int(pid)}, signal.SIGKILL)",
        )

        recovery_deadline = time.monotonic() + WAIT_SECONDS
        while time.monotonic() < recovery_deadline:
            with SessionLocal() as db:
                run = db.execute(select(WorkflowRun).where(WorkflowRun.id == run_id)).scalar_one()
                executions = list(db.execute(
                    select(AgentExecution).where(AgentExecution.workflow_run_id == run_id)
                ).scalars())
            if run.status in {RunStatus.COMPLETED, RunStatus.FAILED}:
                break
            time.sleep(0.1)
        if run.status != RunStatus.COMPLETED:
            raise SystemExit(f"Redelivered investigation ended as {run.status.value}.")

        fake_calls = int(test_client.get(FAKE_CALLS) or 0)
        budget_delta = used_today() - budget_before
        planner_count = sum(item.agent_name == "planner" for item in executions)
        if planner_count != 1:
            raise SystemExit(
                f"Planner executed {planner_count} times; expected one saved checkpoint."
            )
        if fake_calls != budget_delta:
            raise SystemExit(
                f"Budget charged {budget_delta} calls, fake model invoked {fake_calls}."
            )
        if int(test_client.get(ROOT_CAUSE_ATTEMPTS) or 0) != 2:
            raise SystemExit("The root-cause node did not resume after worker redelivery.")
        print(
            "Killed the prefork child during root_cause after the planner checkpoint; "
            f"redelivery completed run {run_id}, planner executions={planner_count}, "
            f"fake calls={fake_calls}, budget delta={budget_delta}."
        )
    finally:
        if worker_started:
            subprocess.run(["docker", "stop", "-t", "10", worker_name], check=False,
                           capture_output=True, text=True)
        subprocess.run(["docker", "rm", "-f", broker_name], check=False,
                       capture_output=True, text=True)
        if postgres_container:
            subprocess.run(
                ["docker", "network", "disconnect", network, postgres_container],
                check=False,
                capture_output=True,
                text=True,
            )
        subprocess.run(["docker", "network", "rm", network], check=False,
                       capture_output=True, text=True)
        if incident_id is not None and run_id is not None:
            _remove_fixture(incident_id, run_id)
        test_client.close()


if __name__ == "__main__":
    main()
