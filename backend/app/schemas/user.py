from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, EmailStr


class UserCreate(BaseModel):
    name: str
    email: EmailStr
    password: str

class UserLogin(BaseModel):
    email: EmailStr
    password: str

class UserResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    name: str
    email: EmailStr
    role: Literal["admin", "responder", "viewer"]
    created_at: datetime


class UserRoleUpdate(BaseModel):
    role: Literal["admin", "responder", "viewer"]

class TokenResponse(BaseModel):
    access_token: str
    token_type: str
