from app.repositories.comment_repository import CommentRepository
from app.schemas.comment import CommentCreate, CommentUpdate, CommentResponse
from app.models.comment import Comment
from app.core.exceptions import (
    IncidentNotFoundError,
    CommentNotFoundError,
    CommentNotAllowedError,
)
from app.repositories.incident_repository import IncidentRepository


class CommentService:
    def __init__(self,comment_repository: CommentRepository,incident_repository: IncidentRepository):
        self.comment_repository = comment_repository
        self.incident_repository = incident_repository

    def create(self,comment: CommentCreate, incident_id: int, current_user_id: int) -> CommentResponse:
        incident = self.incident_repository.get_by_id(incident_id)

        if incident is None:
            raise IncidentNotFoundError("Incident not found.")

        new_comment = Comment(
            content=comment.content,
            incident_id=incident_id,
            user_id=current_user_id,
        )

        created_comment = self.comment_repository.create(new_comment)

        return CommentResponse.model_validate(created_comment)

    def get_all_comments(self, incident_id: int) -> list[CommentResponse]:
        incident = self.incident_repository.get_by_id(incident_id)

        if incident is None:
            raise IncidentNotFoundError("Incident not found.")

        comments = self.comment_repository.get_by_incident(incident_id)

        return [
            CommentResponse.model_validate(comment)
            for comment in comments
        ]

    def get_comment(self, comment_id: int) -> CommentResponse:
        comment = self.comment_repository.get_by_id(comment_id)

        if comment is None:
            raise CommentNotFoundError("Comment not found.")

        return CommentResponse.model_validate(comment)

    def update_comment(
        self,
        comment_id: int,
        comment: CommentUpdate,
        current_user_id: int,
    ) -> CommentResponse:
        existing_comment = self.comment_repository.get_by_id(comment_id)

        if existing_comment is None:
            raise CommentNotFoundError("Comment not found.")

        if existing_comment.user_id != current_user_id:
            raise CommentNotAllowedError(
                "User not allowed to update comment."
            )

        updated_comment = self.comment_repository.update_comment(
            existing_comment,
            comment.content,
        )

        return CommentResponse.model_validate(updated_comment)

    def delete_comment(self, comment_id: int, current_user_id: int) -> None:
        existing_comment = self.comment_repository.get_by_id(comment_id)

        if existing_comment is None:
            raise CommentNotFoundError("Comment not found.")

        if existing_comment.user_id != current_user_id:
            raise CommentNotAllowedError("User not allowed to delete comment.")

        self.comment_repository.delete_comment(existing_comment)