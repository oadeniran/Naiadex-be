from fastapi import APIRouter

from app.schemas.rubric import Question
from app.services import rubric as rubric_service

router = APIRouter(prefix="/api", tags=["rubric"])


@router.get("/rubric", response_model=list[Question])
def get_rubric():
    return rubric_service.get_rubric()