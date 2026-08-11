from datetime import datetime

from pydantic import BaseModel, ConfigDict

class CommentCreate(BaseModel):
    content: str

class CommentUpdate(BaseModel):
    content: str

class CommentResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    incident_id: int
    user_id: int
    content: str
    created_at: datetime
    updated_at: datetime