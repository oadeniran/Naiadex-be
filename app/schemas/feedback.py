from datetime import datetime
from pydantic import BaseModel


class FeedbackCreate(BaseModel):
    category: str                # "bug" | "idea" | "praise" | "other"
    message: str
    username: str | None = None


class Feedback(FeedbackCreate):
    id: str
    created_at: datetime