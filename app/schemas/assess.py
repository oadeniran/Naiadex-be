from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field

class QuestionSuggestion(BaseModel):
    key: str
    type: str
    selection: Any = None           # str | list[str] | "YES"/"NO" | None
    confidence: float = 0.0
    reason: str | None = None
    needs_human: bool = False


class AnalyzeResponse(BaseModel):
    suggestions: list[QuestionSuggestion]


class OverallRequest(BaseModel):
    answers: dict[str, Any]


class OverallResponse(BaseModel):
    value: str                      # GOOD | MODERATE | POOR
    reason: str | None = None


class AnswerRecord(BaseModel):
    value: Any = None
    side: str | None = None
    source: str = "human"                 # "ai" | "human"
    ai_status: str = "pending"            # "pending" | "done" | "failed" | "na"
    ai_suggestion: Any = None
    ai_confidence: float | None = None
    ai_reason: str | None = None
    needs_human: bool = False


class SiteRef(BaseModel):
    type: str                              # "existing" | "new"
    code: str | None = None
    name: str | None = None
    lat: float | None = None
    lng: float | None = None


class Feelings(BaseModel):
    joy: int | None = None
    serenity: int | None = None
    anger: int | None = None
    fear: int | None = None
    na: list[str] = Field(default_factory=list)


class SubmissionCreate(BaseModel):
    site: SiteRef
    answers: dict[str, AnswerRecord] = Field(default_factory=dict)   # human answers only
    water_height: str | None = None
    feelings: Feelings | None = None
    media: dict[str, str] = Field(default_factory=dict)   # {label: base64 data URI}
    photo_mode: str = "labeled"


class Submission(SubmissionCreate):
    id: str
    created_at: datetime
    username: str | None = None
    status: str = "processing"             # "processing" | "complete" | "partial" | "failed"
    overall: dict[str, Any] | None = None
    gate: dict[str, Any] | None = None     # {label: {ok, reason}}
    reason: str | None = None              # top-level explanation for needs_retake
    finalized_at: datetime | None = None
    synthesis: str | None = None
    photo_mode: str = "labeled"     # "labeled" | "unlabeled"
    title: str | None = None

class SubmissionPatch(BaseModel):
    title: str | None = None

# in app/schemas/assess.py
class OverallDecision(BaseModel):
    value: str                      # GOOD | MODERATE | POOR
    ai_suggested: str | None = None
    source: str = "human"


class SubmissionReviewPatch(BaseModel):
    title: str | None = None
    # confirmed answers: {question_key: {value, side?}} — value may be a
    # single code/bool/string, a list (multi), or {"L":..., "R":...} (side_split)
    answers: dict[str, Any] | None = None
    overall: OverallDecision | None = None
    feelings: Feelings | None = None
    finalize: bool = False