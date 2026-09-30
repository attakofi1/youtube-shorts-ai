from pathlib import Path
from uuid import uuid4

from celery.result import AsyncResult
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field, HttpUrl

from .tasks import create_shorts_job
from .worker import celery_app

app = FastAPI(title="YouTube Shorts AI", version="0.2.0")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_credentials=True, allow_methods=["*"], allow_headers=["*"])
STORAGE = Path("/app/storage")
STORAGE.mkdir(parents=True, exist_ok=True)


class CreateJobRequest(BaseModel):
    youtube_url: HttpUrl
    clips: int = Field(default=10, ge=1, le=50)
    min_duration: int = Field(default=20, ge=10, le=120)
    max_duration: int = Field(default=60, ge=15, le=180)


@app.get("/health")
def health():
    return {"status": "ok", "service": "youtube-shorts-ai"}


@app.post("/api/jobs")
def create_job(request: CreateJobRequest):
    if request.min_duration > request.max_duration:
        raise HTTPException(status_code=400, detail="min_duration must not exceed max_duration")
    job_id = str(uuid4())
    create_shorts_job.delay(job_id, str(request.youtube_url), request.clips, request.min_duration, request.max_duration)
    return {"job_id": job_id, "status": "queued"}


@app.get("/api/jobs/{job_id}")
def job_status(job_id: str):
    result = AsyncResult(job_id, app=celery_app)
    payload = {"job_id": job_id, "status": result.state}
    if isinstance(result.info, dict):
        payload.update(result.info)
    if result.successful():
        payload["result"] = result.result
    if result.failed():
        payload["error"] = str(result.result)
    return payload


@app.get("/api/jobs/{job_id}/clips/{filename}")
def get_clip(job_id: str, filename: str):
    path = STORAGE / job_id / filename
    if not path.is_file() or path.parent != STORAGE / job_id:
        raise HTTPException(status_code=404, detail="Clip not found")
    return FileResponse(path, media_type="video/mp4", filename=filename)
