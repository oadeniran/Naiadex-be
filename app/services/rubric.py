from app.schemas.rubric import Question
from app.services.db import rubric_questions

_cache: list[Question] | None = None


def _doc_to_question(doc: dict) -> Question:
    return Question.model_validate({**doc, "key": doc["_id"]})


def get_rubric(force: bool = False) -> list[Question]:
    """Active questions, ordered. Cached in memory (single dyno = fine)."""
    global _cache
    if _cache is None or force:
        docs = rubric_questions.find({"active": True}).sort("order", 1)
        _cache = [_doc_to_question(d) for d in docs]
    return _cache


def invalidate() -> None:
    global _cache
    _cache = None


def get_question(key: str) -> Question | None:
    return next((q for q in get_rubric() if q.key == key), None)