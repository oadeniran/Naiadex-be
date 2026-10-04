from fastapi import APIRouter

from app.schemas.assess import Submission
from app.services.db import submissions

router = APIRouter(prefix="/api", tags=["explore"])


@router.get("/explore", response_model=list[Submission])
def explore(limit: int = 100):
    docs = (
        submissions.find({"status": "finalized", "deleted": {"$ne": True}}, {"media": 0, "gate": 0})
        .sort("finalized_at", -1)
        .limit(limit)
    )
    out = []
    for d in docs:
        d["id"] = str(d.pop("_id"))
        out.append(d)
    return out