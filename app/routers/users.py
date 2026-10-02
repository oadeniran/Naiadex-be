import secrets

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.services.db import users

router = APIRouter(prefix="/api", tags=["users"])


class ClaimRequest(BaseModel):
    username: str
    token: str | None = None


class ClaimResponse(BaseModel):
    username: str
    token: str


@router.post("/users/claim", response_model=ClaimResponse)
def claim_username(req: ClaimRequest):
    name = req.username.strip().lower()
    if not name:
        raise HTTPException(status_code=400, detail="Username cannot be empty.")

    existing = users.find_one({"_id": name})
    if existing is None:
        token = secrets.token_urlsafe(16)
        users.insert_one({"_id": name, "token": token})
        return ClaimResponse(username=name, token=token)

    # name exists: only the original claimant (matching token) may re-enter
    if req.token and secrets.compare_digest(req.token, existing["token"]):
        return ClaimResponse(username=name, token=existing["token"])

    raise HTTPException(status_code=409, detail="That username is taken. Try another.")