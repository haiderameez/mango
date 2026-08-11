from sqlalchemy.orm import Session
from sqlalchemy import select

from app.models.comment import Comment

class CommentRepository:
    def __init__(self, db: Session):
        self.db = db

    def create(self, comment: Comment) -> Comment:
        self.db.add(comment)
        self.db.commit()
        self.db.refresh(comment)
        return comment

    def get_by_incident(self, incident_id: int) -> list[Comment]:
        statement = select(Comment).where(Comment.incident_id == incident_id)
        return self.db.execute(statement).scalars().all()

    def get_by_id(self, comment_id: int) -> Comment | None:
        statement = select(Comment).where(Comment.id == comment_id)
        return self.db.execute(statement).scalar_one_or_none()

    def update_comment(self, comment: Comment, new_content: str) -> Comment:
        comment.content = new_content
        self.db.commit()
        self.db.refresh(comment)
        return comment

    def delete_comment(self, comment: Comment):
        self.db.delete(comment)
        self.db.commit()