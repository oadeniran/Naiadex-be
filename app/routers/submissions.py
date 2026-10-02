from fastapi import APIRouter, BackgroundTasks, HTTPException
from app.schemas.assess import Submission, SubmissionCreate, SubmissionPatch
from app.services import assess as assess_service
from bson import ObjectId  # add if not already imported
from app.services.db import submissions as _subs  # direct handle for these small ops
from app.schemas.assess import SubmissionReviewPatch

router = APIRouter(prefix="/api", tags=["submissions"])


@router.post("/submissions", response_model=Submission)
def create_submission(
    payload: SubmissionCreate,
    background_tasks: BackgroundTasks,
    username: str | None = None,
):
    doc = assess_service.create_submission(payload, username)
    background_tasks.add_task(assess_service.run_assessment, doc["id"])
    return doc


@router.get("/submissions", response_model=list[Submission])
def list_submissions(username: str | None = None, limit: int = 50):
    return assess_service.list_submissions(username, limit)


@router.get("/submissions/{submission_id}", response_model=Submission)
def get_submission(submission_id: str):
    doc = assess_service.get_submission(submission_id)
    if not doc:
        raise HTTPException(status_code=404, detail="Submission not found.")
    return doc


@router.post("/submissions/{submission_id}/resume", response_model=Submission)
def resume_submission(submission_id: str, background_tasks: BackgroundTasks):
    doc = assess_service.get_submission(submission_id)
    if not doc:
        raise HTTPException(status_code=404, detail="Submission not found.")
    background_tasks.add_task(assess_service.run_assessment, submission_id)
    return doc


@router.delete("/submissions/{submission_id}")
def delete_submission(submission_id: str):
    res = _subs.update_one({"_id": ObjectId(submission_id)}, {"$set": {"deleted": True}})
    if res.modified_count == 0:
        raise HTTPException(status_code=404, detail="Submission not found.")
    return {"deleted": submission_id}

@router.patch("/submissions/{submission_id}", response_model=Submission)
def patch_submission(submission_id: str, patch: SubmissionReviewPatch):
    try:
        doc = assess_service.apply_review(submission_id, patch)
    except ValueError as e:
        raise HTTPException(status_code=409, detail=str(e))
    if not doc:
        raise HTTPException(status_code=404, detail="Submission not found.")
    return doc