from fastapi import APIRouter, File, Form, HTTPException, UploadFile

from app.schemas.identify import Observation, IdentificationIn, AcceptIn, CommentIn, LocationIn
from app.services import identify as identify_service

router = APIRouter(prefix="/api", tags=["identify"])


@router.post("/identify", response_model=Observation)
async def identify(
    image: UploadFile = File(...),
    lat: float | None = Form(None),
    lng: float | None = Form(None),
    username: str | None = Form(None),
):
    if not image.content_type or not image.content_type.startswith("image/"):
        raise HTTPException(status_code=400, detail="Please upload an image file.")
    image_bytes = await image.read()
    if not image_bytes:
        raise HTTPException(status_code=400, detail="Empty image upload.")
    try:
        return identify_service.identify_waterlife(
            image_bytes, image.content_type, lat, lng, username
        )
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Identification failed: {e}")

@router.get("/observations", response_model=list[Observation])
def list_observations(limit: int = 50, username: str | None = None):
    return identify_service.list_observations(limit, username)

@router.get("/observations/all", response_model=list[Observation])
def list_all_observations(limit: int = 100):
    return identify_service.list_all_observations(limit)

@router.get("/observations/{obs_id}", response_model=Observation)
def get_observation(obs_id: str):
    doc = identify_service.get_observation(obs_id)
    if not doc:
        raise HTTPException(status_code=404, detail="Observation not found.")
    return doc


@router.post("/observations/{obs_id}/identifications", response_model=Observation)
def add_identification(obs_id: str, body: IdentificationIn):
    if not body.common_name.strip():
        raise HTTPException(status_code=400, detail="A common name is required.")
    doc = identify_service.add_identification(obs_id, body.by, body.common_name, body.scientific_name)
    if not doc:
        raise HTTPException(status_code=404, detail="Observation not found.")
    return doc


@router.post("/observations/{obs_id}/accept", response_model=Observation)
def accept_identification(obs_id: str, body: AcceptIn, ident_id: str):
    try:
        doc = identify_service.accept_identification(obs_id, ident_id, body.by)
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    if not doc:
        raise HTTPException(status_code=404, detail="Observation not found.")
    return doc


@router.post("/observations/{obs_id}/comments", response_model=Observation)
def add_comment(obs_id: str, body: CommentIn):
    if not body.text.strip():
        raise HTTPException(status_code=400, detail="Comment can't be empty.")
    doc = identify_service.add_comment(obs_id, body.by, body.text)
    if not doc:
        raise HTTPException(status_code=404, detail="Observation not found.")
    return doc

@router.patch("/observations/{obs_id}/location", response_model=Observation)
def set_observation_location(obs_id: str, body: LocationIn):
    try:
        doc = identify_service.set_location(obs_id, body.lat, body.lng, body.by)
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e))
    if not doc:
        raise HTTPException(status_code=404, detail="Observation not found.")
    return doc