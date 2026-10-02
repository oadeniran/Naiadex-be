from pydantic import BaseModel, Field
from datetime import datetime


class IdentifyResult(BaseModel):
    common_name: str
    scientific_name: str | None = None
    category: str | None = None
    confidence: float  # expected 0-1
    is_water_related: bool
    notes: str | None = None


class IdentifyResponse(BaseModel):
    result: IdentifyResult
    lat: float | None = None
    lng: float | None = None

class Identification(BaseModel):
    id: str                               # unique within the observation
    by: str                               # "AI" or a username
    source: str                           # "ai" | "human"
    common_name: str
    scientific_name: str | None = None
    confidence: float | None = None       # only for the AI one
    created_at: datetime


class Comment(BaseModel):
    id: str
    by: str
    text: str
    created_at: datetime

class ObservationReview(BaseModel):
    common_name: str | None = None
    scientific_name: str | None = None
    publish: bool = False


class Observation(BaseModel):
    id: str
    created_at: datetime
    result: IdentifyResult
    lat: float | None = None
    lng: float | None = None
    username: str | None = None
    image_mime: str | None = None
    image_url: str | None = None      # base64 data URI now; real URL later
    status: str = "unreviewed"            # "unreviewed" | "reviewed"
    identifications: list[Identification] = Field(default_factory=list)
    accepted_id: str | None = None        # id of the current main identification
    comments: list[Comment] = Field(default_factory=list)


class IdentificationIn(BaseModel):
    by: str
    common_name: str
    scientific_name: str | None = None


class AcceptIn(BaseModel):
    by: str


class CommentIn(BaseModel):
    by: str
    text: str

class LocationIn(BaseModel):
    lat: float
    lng: float
    by: str