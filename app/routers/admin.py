import base64
import os

from fastapi import APIRouter, Depends, File, Header, HTTPException, UploadFile

from app.schemas.rubric import Question, QuestionUpdate
from app.services import rubric as rubric_service
from app.services.db import rubric_questions
from app.schemas.sites import Site
from app.services.db import sites as sites_col

router = APIRouter(prefix="/api/admin", tags=["admin"])


def require_admin(x_admin_token: str | None = Header(None)):
    expected = os.getenv("ADMIN_TOKEN")
    if not expected:
        return  # no token configured -> open (dev convenience)
    if x_admin_token != expected:
        raise HTTPException(status_code=401, detail="Invalid admin token.")


def _doc_to_question(doc: dict) -> Question:
    return Question.model_validate({**doc, "key": doc["_id"]})


@router.get("/rubric", response_model=list[Question], dependencies=[Depends(require_admin)])
def list_all_questions():
    docs = rubric_questions.find().sort("order", 1)  # includes inactive
    return [_doc_to_question(d) for d in docs]


@router.post("/rubric", response_model=Question, dependencies=[Depends(require_admin)])
def create_question(q: Question):
    if rubric_questions.find_one({"_id": q.key}):
        raise HTTPException(status_code=409, detail="Question key already exists.")
    doc = q.model_dump()
    doc["_id"] = doc.pop("key")
    rubric_questions.insert_one(doc)
    rubric_service.invalidate()
    return q


@router.patch("/rubric/{key}", response_model=Question, dependencies=[Depends(require_admin)])
def update_question(key: str, patch: QuestionUpdate):
    if not rubric_questions.find_one({"_id": key}):
        raise HTTPException(status_code=404, detail="Question not found.")
    updates = patch.model_dump(exclude_unset=True)
    if updates:
        rubric_questions.update_one({"_id": key}, {"$set": updates})
    rubric_service.invalidate()
    doc = rubric_questions.find_one({"_id": key})
    return _doc_to_question(doc)


@router.delete("/rubric/{key}", dependencies=[Depends(require_admin)])
def delete_question(key: str, hard: bool = False):
    if hard:
        res = rubric_questions.delete_one({"_id": key})
        if res.deleted_count == 0:
            raise HTTPException(status_code=404, detail="Question not found.")
    else:
        res = rubric_questions.update_one({"_id": key}, {"$set": {"active": False}})
        if res.matched_count == 0:
            raise HTTPException(status_code=404, detail="Question not found.")
    rubric_service.invalidate()
    return {"deleted": key, "hard": hard}


@router.put("/rubric/{key}/options/{code}/image", dependencies=[Depends(require_admin)])
async def set_option_image(key: str, code: str, image: UploadFile = File(...)):
    if not rubric_questions.find_one({"_id": key}):
        raise HTTPException(status_code=404, detail="Question not found.")
    data = await image.read()
    b64 = base64.b64encode(data).decode("ascii")
    image_ref = f"data:{image.content_type};base64,{b64}"
    res = rubric_questions.update_one(
        {"_id": key, "options.code": code},
        {"$set": {"options.$.image_ref": image_ref}},
    )
    if res.matched_count == 0:
        raise HTTPException(status_code=404, detail="Option not found.")
    rubric_service.invalidate()
    return {"updated": f"{key}:{code}"}

@router.get("/sites", response_model=list[Site], dependencies=[Depends(require_admin)])
def admin_list_sites():
    docs = sites_col.find().sort("code", 1)
    return [Site.model_validate({k: v for k, v in d.items() if k != "_id"}) for d in docs]


@router.put("/sites/{code}", response_model=Site, dependencies=[Depends(require_admin)])
def admin_upsert_site(code: str, site: Site):
    doc = site.model_dump()
    doc["code"] = code                       # path is the source of truth
    sites_col.replace_one({"code": code}, doc, upsert=True)
    return Site.model_validate(doc)


@router.delete("/sites/{code}", dependencies=[Depends(require_admin)])
def admin_delete_site(code: str):
    res = sites_col.delete_one({"code": code})
    if res.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Site not found.")
    return {"deleted": code}