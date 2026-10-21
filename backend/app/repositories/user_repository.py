from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.user import User


class UserRepository:
    def __init__(self, db: Session):
        self.db = db

    def create(self, user: User) -> User:
        self.db.add(user)
        self.db.commit()
        self.db.refresh(user)
        return user

    def get_by_email(self, email: str) -> User | None:
        statement = select(User).where(User.email == email)
        return self.db.execute(statement).scalar_one_or_none()

    def get_by_id(self, user_id: int) -> User | None:
        statement = select(User).where(User.id == user_id)
        return self.db.execute(statement).scalar_one_or_none()

    def update_role(self, user: User, role: str) -> User:
        user.role = role
        self.db.commit()
        self.db.refresh(user)
        return user

    def count_by_role(self, role: str) -> int:
        return self.db.scalar(select(func.count()).select_from(User).where(User.role == role)) or 0
