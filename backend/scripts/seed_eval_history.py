"""Load synthetic resolved history into an isolated, migrated ``*_test`` database."""

from datetime import UTC, datetime

from sqlalchemy.engine import make_url

from app.core.config import settings
from app.database.session import SessionLocal
from app.models.incident import Incident, SeverityLevel, StatusLevel
from app.models.user import User
from app.models.workflow import AgentExecution, RunStatus, WorkflowRun
from evals.history_seed import history_records


def main() -> None:
    database_name = make_url(settings.database_url).database or ""
    if not database_name.endswith("_test"):
        raise SystemExit("Refusing to seed history: DATABASE_URL must name a *_test database.")

    records = history_records()
    with SessionLocal() as db:
        if db.query(Incident).count() or db.query(User).count():
            raise SystemExit("Refusing to seed a non-empty test database; use a fresh *_test DB.")

        user = User(
            name="Synthetic history fixture",
            email="eval-history@example.invalid",
            password_hash="not-a-login",
            role="responder",
        )
        db.add(user)
        db.flush()
        now = datetime.now(UTC)

        for item in records:
            incident = Incident(
                title=item["title"],
                description=item["description"],
                severity=SeverityLevel.HIGH,
                status=StatusLevel.RESOLVED,
                created_by=user.id,
                service=item["service"],
                created_at=datetime.fromisoformat(item["resolved_at"]),
                updated_at=datetime.fromisoformat(item["resolved_at"]),
                last_seen_at=datetime.fromisoformat(item["resolved_at"]),
            )
            db.add(incident)
            db.flush()
            run = WorkflowRun(
                incident_id=incident.id,
                status=RunStatus.COMPLETED,
                triggered_by="eval-history-seed",
                started_at=now,
                finished_at=now,
                report=f"Synthetic resolved history: {item['seed_id']}",
            )
            db.add(run)
            db.flush()
            db.add_all(
                [
                    AgentExecution(
                        workflow_run_id=run.id,
                        agent_name="root_cause",
                        status=RunStatus.COMPLETED,
                        started_at=now,
                        finished_at=now,
                        output={"likely_cause": item["likely_cause"]},
                    ),
                    AgentExecution(
                        workflow_run_id=run.id,
                        agent_name="fix_recommendation",
                        status=RunStatus.COMPLETED,
                        started_at=now,
                        finished_at=now,
                        output={"actions": [item["resolution"]]},
                    ),
                ]
            )

        db.commit()
    print(f"Seeded {len(records)} synthetic resolved history cases into {database_name}.")


if __name__ == "__main__":
    main()
