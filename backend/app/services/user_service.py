from app.core.exceptions import InvalidCredentialsError, UserAlreadyExistsError, UserNotFoundError
from app.core.security import create_access_token, hash_password, verify_password
from app.models.user import User
from app.repositories.user_repository import UserRepository
from app.schemas.user import UserCreate, UserLogin


class UserService:
    def __init__(self, repository: UserRepository):
        self.repository = repository

    def register_user(self, user_data: UserCreate) -> User:
        existing_user = self.repository.get_by_email(user_data.email)

        if existing_user:
            raise UserAlreadyExistsError(f"User with email {user_data.email} already exists.")

        new_user = User(
            name=user_data.name,
            email=user_data.email,
            password_hash=hash_password(user_data.password),
        )

        return self.repository.create(new_user)

    def login_user(self, user_data: UserLogin) -> str:
        existing_user = self.repository.get_by_email(user_data.email)

        if not existing_user:
            raise InvalidCredentialsError("Invalid email or password.")

        if not verify_password(user_data.password, existing_user.password_hash):
            raise InvalidCredentialsError("Invalid email or password.")

        return create_access_token({"sub": str(existing_user.id)})

    def set_role(self, user_id: int, role: str) -> User:
        user = self.repository.get_by_id(user_id)
        if user is None:
            raise UserNotFoundError("User not found.")
        if user.role == "admin" and role != "admin" and self.repository.count_by_role("admin") <= 1:
            raise ValueError("The last administrator cannot be demoted.")
        return self.repository.update_role(user, role)
