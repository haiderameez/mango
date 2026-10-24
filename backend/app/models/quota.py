from sqlalchemy import Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.database.base import Base


class DailyLLMBudget(Base):
    __tablename__ = "daily_llm_budgets"

    quota_date: Mapped[str] = mapped_column(String(10), primary_key=True)
    used: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
