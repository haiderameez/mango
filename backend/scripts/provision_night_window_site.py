"""Provision the Night Window Coffee log source in an already migrated Mango database.

Run after ``python -m scripts.seed_demo``. The generated ingest key is shown once; keep it
in the sample site's environment, never in source control.
"""
import argparse

from sqlalchemy.orm import Session

from app.database.session import SessionLocal
from app.models.ingest import DetectionRule
from app.repositories.ingest_repository import IngestRepository
from app.repositories.user_repository import UserRepository
from app.services.ingest_service import IngestService

DEFAULT_SERVICE = "night-window-coffee"
RULE_PATTERN = "simulated payment gateway unavailable"


def ensure_detection_rule(db: Session, service: str = DEFAULT_SERVICE) -> bool:
    repository = IngestRepository(db)
    if any(
        rule.service == service and rule.pattern == RULE_PATTERN
        for rule in repository.get_active_rules()
    ):
        return False

    repository.add_rule(
        DetectionRule(
            service=service,
            level="ERROR",
            threshold=3,
            window_seconds=60,
            pattern=RULE_PATTERN,
        )
    )
    return True


def provision(db: Session, email: str, service: str = DEFAULT_SERVICE) -> tuple[str, bool]:
    user = UserRepository(db).get_by_email(email)
    if user is None:
        raise ValueError(f"Mango user {email!r} does not exist; seed or register it first.")
    rule_created = ensure_detection_rule(db, service)
    key = IngestService.create_key(db, service, user.id)
    return key, rule_created


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--email", default="demo@mango.dev", help="Existing Mango user")
    parser.add_argument("--service", default=DEFAULT_SERVICE, help="Exact log service name")
    args = parser.parse_args()

    with SessionLocal() as db:
        key, rule_created = provision(db, args.email, args.service)

    print(f"Detection rule {'created' if rule_created else 'already exists'} for {args.service}.")
    print(f"MANGO_INGEST_KEY={key}")


if __name__ == "__main__":
    main()
