from datetime import UTC, datetime, timedelta

import jwt
from jwt.exceptions import InvalidTokenError as JWTInvalidTokenError
from pwdlib import PasswordHash

from app.core.config import settings
from app.core.exceptions import InvalidAccessTokenError

password_hash = PasswordHash.recommended()

def hash_password(password: str) -> str:
    return password_hash.hash(password)

def verify_password(password: str, hashed_password: str) -> bool:
    return password_hash.verify(password, hashed_password)

def create_access_token(data: dict) -> str:
    to_encode = data.copy()

    expire = datetime.now(UTC) + timedelta(minutes=settings.jwt_expiration_minutes)

    to_encode.update({"exp": expire})

    return jwt.encode(
        to_encode,
        settings.jwt_secret_key,
        algorithm=settings.jwt_algorithm,
    )

def decode_access_token(token: str) -> dict:
    try:
        payload = jwt.decode(
            token,
            settings.jwt_secret_key,
            algorithms=[settings.jwt_algorithm],
        )

        if "sub" not in payload:
            raise InvalidAccessTokenError("Invalid access token.")

        return payload

    except JWTInvalidTokenError as error:
        raise InvalidAccessTokenError("Invalid access token.") from error