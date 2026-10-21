from datetime import datetime

from sqlalchemy import String, cast, or_, select
from sqlalchemy.orm import Session

from app.models.ingest import DetectionRule, LogRecord, ServiceIngestKey


class IngestRepository:
    def __init__(self, db: Session):
        self.db = db

    def get_key_by_hash(self, key_hash: str) -> ServiceIngestKey | None:
        statement = select(ServiceIngestKey).where(
            ServiceIngestKey.key_hash == key_hash, ServiceIngestKey.active.is_(True)
        )
        return self.db.execute(statement).scalar_one_or_none()

    def get_active_key(self, key_id: int) -> ServiceIngestKey | None:
        statement = select(ServiceIngestKey).where(
            ServiceIngestKey.id == key_id, ServiceIngestKey.active.is_(True)
        )
        return self.db.execute(statement).scalar_one_or_none()

    def add_key(self, key: ServiceIngestKey) -> ServiceIngestKey:
        self.db.add(key)
        self.db.commit()
        self.db.refresh(key)
        return key

    def add_records(self, records: list[LogRecord]) -> None:
        self.db.add_all(records)
        self.db.commit()

    def get_active_rules(self) -> list[DetectionRule]:
        statement = select(DetectionRule).where(DetectionRule.active.is_(True))
        return list(self.db.execute(statement).scalars())

    def get_window(
        self,
        start: datetime,
        end: datetime,
        limit: int,
        *,
        service: str | None = None,
        levels: set[str] | None = None,
        keyword: str | None = None,
    ) -> list[LogRecord]:
        statement = select(LogRecord).where(LogRecord.ts >= start, LogRecord.ts <= end)
        if service is not None:
            statement = statement.where(LogRecord.service == service)
        if levels is not None:
            statement = statement.where(LogRecord.level.in_(levels))
        if keyword:
            match = f"%{keyword}%"
            statement = statement.where(
                or_(
                    LogRecord.message.ilike(match),
                    LogRecord.request_id.ilike(match),
                    cast(LogRecord.context, String).ilike(match),
                )
            )
        statement = statement.order_by(LogRecord.ts.desc(), LogRecord.id.desc()).limit(limit)
        return list(self.db.execute(statement).scalars())
