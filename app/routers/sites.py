from fastapi import APIRouter, HTTPException

from app.schemas.sites import Site, UserSite, UserSiteCreate
from app.services.db import sites as sites_col
from app.services.db import user_sites as user_sites_col

from bson import ObjectId

router = APIRouter(prefix="/api", tags=["sites"])


@router.get("/sites", response_model=list[Site])
def get_sites():
    docs = sites_col.find({}, {"polygon": 0}).sort("code", 1)
    return [Site.model_validate({k: v for k, v in d.items() if k != "_id"}) for d in docs]


@router.get("/sites/mine", response_model=list[UserSite])
def get_my_sites(username: str):
    docs = user_sites_col.find({"username": username}).sort("name", 1)
    return [
        UserSite(
            id=str(d["_id"]),
            username=d["username"],
            name=d["name"],
            latitude=d["latitude"],
            longitude=d["longitude"],
        )
        for d in docs
    ]

@router.post("/sites/mine", response_model=UserSite)
def create_my_site(payload: UserSiteCreate, username: str):
    if not username.strip():
        raise HTTPException(status_code=400, detail="username is required")
    doc = {**payload.model_dump(), "username": username}
    inserted = user_sites_col.insert_one(doc)
    return UserSite(id=str(inserted.inserted_id), **doc)

@router.delete("/sites/mine/{site_id}")
def delete_my_site(site_id: str, username: str):
    res = user_sites_col.delete_one({"_id": ObjectId(site_id), "username": username})
    if res.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Site not found.")
    return {"deleted": site_id}

@router.get("/sites/{code}", response_model=Site)
def get_site(code: str):
    doc = sites_col.find_one({"code": code})
    if not doc:
        raise HTTPException(status_code=404, detail="Site not found.")
    return Site.model_validate({k: v for k, v in doc.items() if k != "_id"})