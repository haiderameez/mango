from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.database.session import get_db
from app.repositories.user_repository import UserRepository
from app.schemas.user import UserCreate, UserResponse, UserLogin, TokenResponse
from app.services.user_service import UserService
from app.core.exceptions import UserAlreadyExistsError, InvalidCredentialsError
from app.core.dependencies import get_current_user
from app.models.user import User    

router = APIRouter(
    prefix="/auth",
    tags=["authentication"],
)

def get_user_service(db: Session = Depends(get_db)) -> UserService:
    repository = UserRepository(db)
    return UserService(repository)

@router.post("/register",
             response_model=UserResponse,
             status_code=status.HTTP_201_CREATED
)

def register_user(user_data: UserCreate, service: UserService = Depends(get_user_service)):
    try:
        return service.register_user(user_data)

    except UserAlreadyExistsError as e:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(e)
        )

@router.post("/login",
             response_model=TokenResponse,
             status_code=status.HTTP_200_OK)

def login_user(user_data: UserLogin, service: UserService = Depends(get_user_service)):
    try:
        token = service.login_user(user_data)
        return TokenResponse(access_token=token, token_type="bearer")

    except InvalidCredentialsError as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=str(e)
        )

@router.get("/me",
            response_model=UserResponse,
             status_code=status.HTTP_200_OK)

def get_me(current_user: User = Depends(get_current_user)):
    return current_user