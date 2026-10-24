from sqlalchemy import delete, select
from sqlalchemy.dialects.postgresql import insert as postgres_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.orm import Session

from app.models.quota import DailyLLMBudget


class QuotaRepository:
    def __init__(self, db: Session):
        self.db = db

    def used(self, quota_date: str) -> int:
        value = self.db.execute(
            select(DailyLLMBudget.used).where(DailyLLMBudget.quota_date == quota_date)
        ).scalar_one_or_none()
        return value or 0

    def consume(self, quota_date: str, requests: int, limit: int) -> bool:
        if requests <= 0:
            raise ValueError("request count must be positive")
        if requests > limit:
            return False
        dialect = self.db.bind.dialect.name
        insert = postgres_insert if dialect == "postgresql" else sqlite_insert
        statement = insert(DailyLLMBudget).values(quota_date=quota_date, used=requests)
        statement = statement.on_conflict_do_update(
            index_elements=[DailyLLMBudget.quota_date],
            set_={"used": DailyLLMBudget.used + requests},
            where=DailyLLMBudget.used + requests <= limit,
        ).returning(DailyLLMBudget.used)
        consumed = self.db.execute(statement).scalar_one_or_none()
        self.db.commit()
        return consumed is not None and consumed <= limit

    def clear(self) -> None:
        self.db.execute(delete(DailyLLMBudget))
        self.db.commit()
