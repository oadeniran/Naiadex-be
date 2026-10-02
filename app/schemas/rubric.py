from enum import Enum

from pydantic import BaseModel, Field


class QuestionType(str, Enum):
    single = "single"   # pick exactly one code
    multi = "multi"     # pick zero-or-more codes
    yesno = "yesno"     # YES / NO / (unsure -> needs_human)
    value = "value"     # free text/number, human-only


class LabeledImage(BaseModel):
    label: str          # what to tell the LLM this image shows
    image: str          # base64 data URI


class Option(BaseModel):
    code: str
    display_name: str
    images: list[LabeledImage] = Field(default_factory=list)   # was image_ref
    order: int = 0


class Question(BaseModel):
    key: str
    prompt: str
    help_text: str | None = None
    type: QuestionType
    side_split: bool = False
    ai_enabled: bool = True
    ai_hint: str | None = None
    source_photos: list[str] = Field(default_factory=list)
    order: int = 0
    active: bool = True
    example_images: list[LabeledImage] = Field(default_factory=list)   # now labeled
    options: list[Option] = Field(default_factory=list)


class QuestionUpdate(BaseModel):
    """Partial update for admin PATCH; only sent fields are applied."""
    prompt: str | None = None
    help_text: str | None = None
    type: QuestionType | None = None
    side_split: bool | None = None
    ai_enabled: bool | None = None
    ai_hint: str | None = None
    source_photos: list[str] | None = None
    order: int | None = None
    active: bool | None = None
    options: list[Option] | None = None