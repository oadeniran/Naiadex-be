
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import init_env
import asyncio
from app.routers import admin, assess, identify, rubric, sites, submissions, users, explore, feedback

app = FastAPI(title="OAH Assist API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
async def _resume_pending():
    from app.services import assess as assess_service

    async def _sweep():
        for sid in assess_service.pending_submission_ids():
            asyncio.create_task(asyncio.to_thread(assess_service.run_assessment, sid))

    # fire and forget; don't block startup
    asyncio.create_task(_sweep())


@app.get("/api/health")
def health():
    return {"status": "ok", "service": "oah-assist-api"}


app.include_router(identify.router)
app.include_router(users.router)
app.include_router(rubric.router)
app.include_router(assess.router)
app.include_router(submissions.router)
app.include_router(sites.router)
app.include_router(admin.router)
app.include_router(feedback.router)
app.include_router(explore.router)