"""Create a hashed ingest key: python -m scripts.create_ingest_key SERVICE EMAIL."""
import argparse

from sqlalchemy import select

from app.database.session import SessionLocal
from app.models.user import User
from app.services.ingest_service import IngestService


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("service", help="Exact service name accepted in log records")
    parser.add_argument("email", help="Existing Mango user that owns detected incidents")
    args = parser.parse_args()
    with SessionLocal() as db:
        user = db.execute(select(User).where(User.email == args.email)).scalar_one_or_none()
        if user is None:
            parser.error("User email does not exist")
        key = IngestService.create_key(db, args.service, user.id)
    print(f"Store this key in the service's secret manager; it will not be shown again:\n{key}")


if __name__ == "__main__":
    main()
