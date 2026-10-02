from fastapi import APIRouter, File, HTTPException, UploadFile

from app.schemas.assess import AnalyzeResponse, OverallRequest, OverallResponse
from app.services import assess as assess_service

router = APIRouter(prefix="/api/assess", tags=["assess"])


@router.post("/analyze", response_model=AnalyzeResponse)
async def analyze(
    upstream: UploadFile | None = File(None),
    downstream: UploadFile | None = File(None),
    context: UploadFile | None = File(None),
    biodiversity: UploadFile | None = File(None),
):
    labeled = []
    for label, f in [
        ("upstream", upstream),
        ("downstream", downstream),
        ("context", context),
        ("biodiversity", biodiversity),
    ]:
        if f is not None:
            data = await f.read()
            if data:
                labeled.append((label, data, f.content_type or "image/jpeg"))
    if not labeled:
        raise HTTPException(status_code=400, detail="Upload at least one photo.")
    try:
        return assess_service.analyze_photos(labeled)
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Analysis failed: {e}")


@router.post("/overall", response_model=OverallResponse)
def overall(req: OverallRequest):
    try:
        return assess_service.suggest_overall(req.answers)
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Overall failed: {e}")