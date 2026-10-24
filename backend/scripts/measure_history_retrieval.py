"""Measure pgvector retrieval against 50 synthetic resolved incidents.

Run from backend against a disposable database whose name ends in ``_test``:
``DATABASE_URL=... python -m scripts.measure_history_retrieval``. All inserted rows are
rolled back, and no embedding provider is called.
"""
from time import perf_counter

from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session

from app.core.config import settings
from app.database.session import engine
from app.models.incident import Incident, SeverityLevel, StatusLevel
from app.models.incident_embedding import IncidentEmbedding
from app.models.user import User
from app.models.workflow import AgentExecution, RunStatus, WorkflowRun
from app.repositories.incident_history_repository import IncidentHistoryRepository


def main() -> None:
    database = make_url(settings.database_url).database or ""
    if not database.endswith("_test"):
        raise SystemExit(
            "Refusing to write test fixtures: DATABASE_URL must name a *_test database."
        )

    with Session(engine) as db:
        try:
            user = User(
                name="History retrieval test",
                email="history-retrieval-test@example.invalid",
                password_hash="not-a-login",
            )
            db.add(user)
            db.flush()
            expected_id = None
            for index in range(50):
                incident = Incident(
                    title=f"Synthetic fault family {index}",
                    description="synthetic prior incident",
                    severity=SeverityLevel.HIGH,
                    status=StatusLevel.RESOLVED,
                    created_by=user.id,
                )
                db.add(incident)
                db.flush()
                if index == 17:
                    expected_id = incident.id
                run = WorkflowRun(
                    incident_id=incident.id,
                    status=RunStatus.COMPLETED,
                    triggered_by="history-retrieval-test",
                )
                db.add(run)
                db.flush()
                cause = "known connection pool leak" if index == 17 else f"other cause {index}"
                db.add_all(
                    [
                        AgentExecution(
                            workflow_run_id=run.id,
                            agent_name="root_cause",
                            status=RunStatus.COMPLETED,
                            output={"likely_cause": cause},
                        ),
                        AgentExecution(
                            workflow_run_id=run.id,
                            agent_name="fix_recommendation",
                            status=RunStatus.COMPLETED,
                            output={"actions": ["recycle workers"]},
                        ),
                    ]
                )
                vector = [0.0] * 768
                vector[0 if index == 17 else index + 1] = 1.0
                db.add(IncidentEmbedding(incident_id=incident.id, embedding=vector))

            db.flush()
            started = perf_counter()
            matches = IncidentHistoryRepository(db).search(
                [1.0] + [0.0] * 767, limit=3, floor=0.75
            )
            elapsed_ms = (perf_counter() - started) * 1000
            if not matches or matches[0]["incident_id"] != expected_id:
                raise SystemExit("Known incident was not returned as the top history match.")
            print(
                f"50 resolved-vector fixtures -> top match #{matches[0]['incident_id']} "
                f"(expected #{expected_id}), {elapsed_ms:.2f} ms"
            )
            print(f"cause={matches[0]['likely_cause']}; matches={len(matches)}")
        finally:
            db.rollback()


if __name__ == "__main__":
    main()
