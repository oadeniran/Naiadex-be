from datetime import datetime, timezone

from app.prompts.identify import IDENTIFY_PROMPT
from app.schemas.identify import IdentifyResult, Observation
from app.services import gemini
from app.services.db import observations
import base64
from datetime import datetime, timezone
from bson import ObjectId
import secrets

# in _to_observation, add image_url from the doc:
def _to_observation(doc: dict, result: IdentifyResult, _id: str) -> Observation:
    return Observation(
        id=_id,
        created_at=doc["created_at"],
        result=result,
        lat=doc.get("lat"),
        lng=doc.get("lng"),
        image_mime=doc.get("image_mime"),
        username=doc.get("username"),
        image_url=doc.get("image_url"),
        status=doc.get("status", "unreviewed"),
        identifications=doc.get("identifications", []),
        accepted_id=doc.get("accepted_id"),
        comments=doc.get("comments", []),
    )

def identify_waterlife(
    image_bytes: bytes,
    mime_type: str,
    lat: float | None = None,
    lng: float | None = None,
    username: str | None = None,
) -> Observation:
    data = gemini.json_from_image(image_bytes, mime_type, IDENTIFY_PROMPT)
    result = IdentifyResult.model_validate(data)

    encoded = base64.b64encode(image_bytes).decode("ascii")
    image_url = f"data:{mime_type};base64,{encoded}"

    ai_ident = {
        "id": secrets.token_hex(6),
        "by": "AI",
        "source": "ai",
        "common_name": result.common_name,
        "scientific_name": result.scientific_name,
        "confidence": result.confidence,
        "created_at": datetime.now(timezone.utc),
    }

    doc = {
        "created_at": datetime.now(timezone.utc),
        "result": result.model_dump(),
        "lat": lat,
        "lng": lng,
        "image_mime": mime_type,
        "username": username,
        "image_url": image_url,
        "status": "unreviewed",
        "identifications": [ai_ident],
        "accepted_id": ai_ident["id"],
        "comments": [],
    }
    inserted = observations.insert_one(doc)
    return _to_observation(doc, result, str(inserted.inserted_id))


def get_observation(obs_id: str) -> Observation | None:
    doc = observations.find_one({"_id": ObjectId(obs_id)})
    return _to_observation(doc, IdentifyResult.model_validate(doc["result"]), str(doc["_id"])) if doc else None


def review_observation(
    obs_id: str,
    common_name: str | None,
    scientific_name: str | None,
    publish: bool,
) -> Observation | None:
    oid = ObjectId(obs_id)
    doc = observations.find_one({"_id": oid})
    if not doc:
        return None

    updates = {}
    if common_name is not None:
        updates["human_common_name"] = common_name.strip() or None
    if scientific_name is not None:
        updates["human_scientific_name"] = scientific_name.strip() or None
    if publish:
        updates["status"] = "published"
        updates["reviewed_at"] = datetime.now(timezone.utc)

    if updates:
        observations.update_one({"_id": oid}, {"$set": updates})

    d = observations.find_one({"_id": oid})
    return _to_observation(d, IdentifyResult.model_validate(d["result"]), str(d["_id"]))

def list_observations(limit: int = 50, username: str | None = None) -> list[Observation]:
    query = {"username": username} if username else {}
    docs = observations.find(query).sort("created_at", -1).limit(limit)
    return [
        _to_observation(d, IdentifyResult.model_validate(d["result"]), str(d["_id"]))
        for d in docs
    ]

def list_all_observations(limit: int = 100) -> list[Observation]:
    docs = observations.find().sort("created_at", -1).limit(limit)
    return [
        _to_observation(d, IdentifyResult.model_validate(d["result"]), str(d["_id"]))
        for d in docs
    ]

def add_identification(obs_id: str, by: str, common_name: str, scientific_name: str | None) -> Observation | None:
    oid = ObjectId(obs_id)
    doc = observations.find_one({"_id": oid})
    if not doc:
        return None
    ident = {
        "id": secrets.token_hex(6),
        "by": by or "anonymous",
        "source": "human",
        "common_name": common_name.strip(),
        "scientific_name": (scientific_name or "").strip() or None,
        "confidence": None,
        "created_at": datetime.now(timezone.utc),
    }
    update = {"$push": {"identifications": ident}}
    # if the owner is the one suggesting, auto-accept theirs and mark reviewed
    if by and by == doc.get("username"):
        update["$set"] = {"accepted_id": ident["id"], "status": "reviewed"}
    observations.update_one({"_id": oid}, update)
    return get_observation(obs_id)


def accept_identification(obs_id: str, ident_id: str, by: str) -> Observation | None:
    oid = ObjectId(obs_id)
    doc = observations.find_one({"_id": oid})
    if not doc:
        return None
    if by != doc.get("username"):
        raise PermissionError("Only the owner can accept an identification.")
    if not any(i["id"] == ident_id for i in doc.get("identifications", [])):
        raise ValueError("Identification not found.")
    observations.update_one(
        {"_id": oid},
        {"$set": {"accepted_id": ident_id, "status": "reviewed"}},
    )
    return get_observation(obs_id)


def add_comment(obs_id: str, by: str, text: str) -> Observation | None:
    oid = ObjectId(obs_id)
    if not observations.find_one({"_id": oid}):
        return None
    comment = {
        "id": secrets.token_hex(6),
        "by": by or "anonymous",
        "text": text.strip(),
        "created_at": datetime.now(timezone.utc),
    }
    observations.update_one({"_id": oid}, {"$push": {"comments": comment}})
    return get_observation(obs_id)

def set_location(obs_id: str, lat: float, lng: float, by: str) -> Observation | None:
    oid = ObjectId(obs_id)
    doc = observations.find_one({"_id": oid})
    if not doc:
        return None
    if by != doc.get("username"):
        raise PermissionError("Only the owner can set the location.")
    observations.update_one({"_id": oid}, {"$set": {"lat": lat, "lng": lng}})
    return get_observation(obs_id)