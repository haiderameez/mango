from app.core.security import hash_password, verify_password
from app.models.user import User
from app.repositories.user_repository import UserRepository
from app.schemas.user import UserCreate, UserLogin
from app.core.exceptions import UserAlreadyExistsError, InvalidCredentialsError

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

    def login_user(self, user_data: UserLogin) -> User:
        existing_user = self.repository.get_by_email(user_data.email)

        if not existing_user:
            raise InvalidCredentialsError("Invalid email or password.")

        if not verify_password(user_data.password, existing_user.password_hash):
            raise InvalidCredentialsError("Invalid email or password.")

        return existing_user 