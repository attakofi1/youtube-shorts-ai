from pathlib import Path
from uuid import uuid4

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, HttpUrl, Field

from .tasks import create_shorts_job

app = FastAPI(title="YouTube Shorts AI", version="0.1.0")

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
    create_shorts_job.delay(
        job_id,
        str(request.youtube_url),
        request.clips,
        request.min_duration,
        request.max_duration,
    )
    return {"job_id": job_id, "status": "queued"}
