from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException

from app.schemas.feedback import Feedback, FeedbackCreate
from app.services.db import feedback as feedback_col

router = APIRouter(prefix="/api", tags=["feedback"])


@router.post("/feedback", response_model=Feedback)
def create_feedback(body: FeedbackCreate):
    if not body.message.strip():
        raise HTTPException(status_code=400, detail="Feedback can't be empty.")
    doc = {
        "category": body.category,
        "message": body.message.strip(),
        "username": body.username,
        "created_at": datetime.now(timezone.utc),
    }
    inserted = feedback_col.insert_one(doc)
    return Feedback(id=str(inserted.inserted_id), **doc)


@router.get("/feedback", response_model=list[Feedback])
def list_feedback(limit: int = 100):
    docs = feedback_col.find().sort("created_at", -1).limit(limit)
    return [Feedback(id=str(d["_id"]), category=d["category"], message=d["message"],
                     username=d.get("username"), created_at=d["created_at"]) for d in docs]