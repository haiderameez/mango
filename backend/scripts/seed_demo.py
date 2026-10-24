"""Seed a demonstration dataset: users, incidents, timelines, and real investigations.

    python -m scripts.seed_demo            # from backend/, after `alembic upgrade head`
    python -m scripts.seed_demo --reset    # delete the demo data first

The investigations are not fabricated. `demo_fixtures.json` holds the output of real runs
against real DummyCommerce logs - every agent's reasoning, its duration and the final report
exactly as Gemini produced them - so a deployed demo shows genuine output without needing a
log file or spending an API call.

Timestamps are rebased onto the moment you run this, so the register always reads as current.
"""
import argparse
import json
import pathlib
from datetime import UTC, datetime, timedelta

from sqlalchemy import select

from app.core.security import hash_password
from app.database.session import SessionLocal
from app.models.activity import Activity, ActivityType
from app.models.comment import Comment
from app.models.incident import Incident, SeverityLevel, StatusLevel
from app.models.user import User
from app.models.workflow import AgentExecution, RunStatus, WorkflowRun

FIXTURES = pathlib.Path(__file__).parent / "demo_fixtures.json"

DEMO_PASSWORD = "mango-demo"

USERS = [
    ("Ops", "demo@mango.dev"),
    ("Priya N.", "priya@mango.dev"),
    ("DummyCommerce", "dummycommerce@mango.dev"),
]

#: (fault key or None, title, severity, status, minutes ago, assignee index or None)
INCIDENTS = [
    (
        "dependency_down",
        "Order creation failing: payment gateway unavailable",
        SeverityLevel.HIGH,
        StatusLevel.INVESTIGATING,
        26,
        0,
    ),
    (
        "db_connection",
        "Order creation failing: orders-db connection refused",
        SeverityLevel.CRITICAL,
        StatusLevel.INVESTIGATING,
        95,
        1,
    ),
    (
        None,
        "Order creation failing: unhandled TypeError in pricing",
        SeverityLevel.HIGH,
        StatusLevel.RESOLVED,
        60 * 22,
        0,
    ),
    (
        None,
        "Order creation degraded: responses above latency threshold",
        SeverityLevel.MEDIUM,
        StatusLevel.OPEN,
        60 * 5,
        None,
    ),
    (
        None,
        "Search autocomplete returning 500s intermittently",
        SeverityLevel.MEDIUM,
        StatusLevel.RESOLVED,
        60 * 70,
        1,
    ),
    (
        None,
        "Product images serving stale versions from the CDN",
        SeverityLevel.LOW,
        StatusLevel.OPEN,
        60 * 40,
        None,
    ),
]

DESCRIPTIONS = {
    "Order creation failing: unhandled TypeError in pricing": (
        "POST /orders returned 500: unsupported operand type(s) for *: 'NoneType' and 'int' "
        "in pricing.total(). Started after the PROMO_EXPIRED code was retired."
    ),
    "Order creation degraded: responses above latency threshold": (
        "POST /orders completing but taking 3.2s against a 500ms threshold. "
        "Seq scan on order_items suspected."
    ),
    "Search autocomplete returning 500s intermittently": (
        "Roughly 3% of /search/suggest calls return 500 under load. Not reproducible locally."
    ),
    "Product images serving stale versions from the CDN": (
        "Reported by support: product 2 shows last month's packaging. Cache headers set to "
        "7 days with no purge on publish."
    ),
}

COMMENTS = {
    "Order creation failing: payment gateway unavailable": [
        (1, 18, "Gateway status page is green, so this looks like our side of the connection."),
        (0, 11, "Circuit breaker is open, so we are failing fast rather than queueing. "
                "Holding off on a restart until the investigation finishes."),
    ],
    "Order creation failing: orders-db connection refused": [
        (1, 70, "Pool was already saturated before the connection dropped - see the exhaustion "
                "warnings four lines up."),
    ],
    "Order creation failing: unhandled TypeError in pricing": [
        (0, 60 * 21, "discount_rate comes back None for retired promo codes. One-line guard in "
                     "pricing.total() plus a regression test."),
        (1, 60 * 20, "Shipped. Watching the error rate for an hour before resolving."),
    ],
}

RESOLUTIONS = {
    "Order creation failing: unhandled TypeError in pricing": 60 * 19,
    "Search autocomplete returning 500s intermittently": 60 * 64,
}


def _record(db, incident_id, activity_type, when, user_id=None, detail=None):
    db.add(
        Activity(
            incident_id=incident_id,
            activity_type=activity_type,
            user_id=user_id,
            detail=detail,
            created_at=when,
        )
    )


def _replay(db, incident, fixture, now):
    """Re-create a captured run, with its agent executions, ending a minute ago."""
    executions = fixture["executions"]
    total = sum(_duration(e) for e in executions)
    started = now - timedelta(seconds=total + 60)

    run = WorkflowRun(
        incident_id=incident.id,
        status=RunStatus.COMPLETED,
        triggered_by=fixture["triggered_by"],
        started_at=started,
        finished_at=started + timedelta(seconds=total),
        report=fixture["report"],
        created_at=started,
    )
    db.add(run)
    db.flush()

    at = started

    for execution in executions:
        duration = _duration(execution)
        db.add(
            AgentExecution(
                workflow_run_id=run.id,
                agent_name=execution["agent_name"],
                status=RunStatus[execution["status"]],
                started_at=at,
                finished_at=at + timedelta(seconds=duration),
                output=execution["output"],
                error=execution["error"],
            )
        )
        at += timedelta(seconds=duration)

    _record(
        db,
        incident.id,
        ActivityType.INVESTIGATION_STARTED,
        started,
        detail=f"AI investigation triggered by {fixture['triggered_by']}",
    )
    _record(
        db,
        incident.id,
        ActivityType.INVESTIGATION_COMPLETED,
        run.finished_at,
        detail=f"AI investigation #{run.id} completed",
    )


def _duration(execution):
    started = datetime.fromisoformat(execution["started_at"])
    finished = datetime.fromisoformat(execution["finished_at"])
    return max((finished - started).total_seconds(), 0.4)


def seed(db, reset: bool) -> None:
    existing = db.scalars(select(User).where(User.email.in_([e for _, e in USERS]))).all()

    if existing and not reset:
        raise SystemExit(
            "The demo data is already present. Re-run with --reset to replace it."
        )

    if existing:
        for user in existing:
            for incident in db.scalars(
                select(Incident).where(Incident.created_by == user.id)
            ).all():
                db.delete(incident)  # comments, activity and runs cascade
            db.delete(user)
        db.commit()

    fixtures = {f["fault"]: f for f in json.loads(FIXTURES.read_text(encoding="utf-8"))}
    now = datetime.now(UTC)
    password_hash = hash_password(DEMO_PASSWORD)

    users = [
        User(
            name=name,
            email=email,
            password_hash=password_hash,
            role="admin" if email == "demo@mango.dev" else "responder",
        )
        for name, email in USERS
    ]
    db.add_all(users)
    db.flush()

    reporter = users[2]

    for fault, title, severity, status, minutes, assignee in INCIDENTS:
        created_at = now - timedelta(minutes=minutes)

        incident = Incident(
            title=title,
            description=DESCRIPTIONS.get(title) or fixtures[fault]["description"],
            severity=severity,
            status=status,
            created_by=reporter.id if fault else users[0].id,
            assigned_to=users[assignee].id if assignee is not None else None,
            created_at=created_at,
            updated_at=created_at,
        )
        db.add(incident)
        db.flush()

        _record(
            db,
            incident.id,
            ActivityType.INCIDENT_CREATED,
            created_at,
            user_id=incident.created_by,
            detail=f"Incident created with severity {severity.value}",
        )

        if assignee is not None:
            _record(
                db,
                incident.id,
                ActivityType.ASSIGNED,
                created_at + timedelta(minutes=2),
                user_id=incident.created_by,
                detail=f"Assigned to {users[assignee].name}",
            )

        if status is not StatusLevel.OPEN:
            _record(
                db,
                incident.id,
                ActivityType.STATUS_CHANGED,
                created_at + timedelta(minutes=3),
                user_id=users[0].id,
                detail="Status changed from OPEN to INVESTIGATING",
            )

        if status is StatusLevel.RESOLVED:
            resolved_at = now - timedelta(minutes=RESOLUTIONS[title])
            _record(
                db,
                incident.id,
                ActivityType.STATUS_CHANGED,
                resolved_at,
                user_id=users[0].id,
                detail="Status changed from INVESTIGATING to RESOLVED",
            )

        for author, minutes_ago, content in COMMENTS.get(title, []):
            at = now - timedelta(minutes=minutes_ago)
            db.add(
                Comment(
                    incident_id=incident.id,
                    user_id=users[author].id,
                    content=content,
                    created_at=at,
                    updated_at=at,
                )
            )
            _record(
                db,
                incident.id,
                ActivityType.COMMENT_ADDED,
                at,
                user_id=users[author].id,
                detail="Comment added",
            )

        if fault:
            _replay(db, incident, fixtures[fault], now)

    db.commit()

    print(f"Seeded {len(INCIDENTS)} incidents and {len(fixtures)} investigations.")
    print(f"Sign in at /console as {USERS[0][1]} / {DEMO_PASSWORD}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--reset", action="store_true", help="delete existing demo data first")
    arguments = parser.parse_args()

    db = SessionLocal()
    try:
        seed(db, reset=arguments.reset)
    finally:
        db.close()


if __name__ == "__main__":
    main()
