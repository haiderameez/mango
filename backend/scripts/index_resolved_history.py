"""Backfill vector embeddings for resolved incidents with completed investigations.

Run from backend with ``python -m scripts.index_resolved_history --limit 50``. The
embedding request is batched and charged once to Mango's existing provider budget.
"""
import argparse

from app.database.session import SessionLocal
from app.repositories.incident_history_repository import IncidentHistoryRepository
from app.services.incident_history import IncidentHistoryService


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--limit", type=int, default=500)
    args = parser.parse_args()
    if args.limit < 1:
        parser.error("--limit must be positive")

    with SessionLocal() as db:
        indexed = IncidentHistoryService(IncidentHistoryRepository(db)).index_unindexed_resolved(
            limit=args.limit
        )
    print(f"Indexed {indexed} resolved incident(s).")


if __name__ == "__main__":
    main()
