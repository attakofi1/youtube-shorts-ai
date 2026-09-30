from pathlib import Path
import zipfile
from uuid import uuid4

from celery.result import AsyncResult
from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, Response
from pydantic import BaseModel, Field, HttpUrl

from .tasks import create_shorts_job
from .worker import celery_app

app = FastAPI(title="YouTube Shorts AI", version="0.2.1")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_credentials=True, allow_methods=["*"], allow_headers=["*"])
STORAGE = Path("/app/storage")
STORAGE.mkdir(parents=True, exist_ok=True)


class CreateJobRequest(BaseModel):
    youtube_url: HttpUrl | None = None
    clips: int = Field(default=10, ge=1, le=50)
    min_duration: int = Field(default=20, ge=10, le=120)
    max_duration: int = Field(default=60, ge=15, le=180)
    caption_style: str = Field(default="bold", pattern="^(bold|clean|karaoke)$")
    remove_silence: bool = True
    background_music: bool = False


@app.get("/health")
def health():
    return {"status": "ok", "service": "youtube-shorts-ai"}


@app.post("/api/jobs")
def create_job(request: CreateJobRequest):
    if request.youtube_url is None:
        raise HTTPException(status_code=400, detail="youtube_url is required")
    if request.min_duration > request.max_duration:
        raise HTTPException(status_code=400, detail="min_duration must not exceed max_duration")
    job_id = str(uuid4())
    create_shorts_job.apply_async(args=[job_id, str(request.youtube_url), request.clips, request.min_duration, request.max_duration, None, request.caption_style, request.remove_silence, request.background_music], task_id=job_id)
    return {"job_id": job_id, "status": "queued"}


@app.get("/api/jobs/{job_id}")
def job_status(job_id: str):
    result = AsyncResult(job_id, app=celery_app)
    payload = {"job_id": job_id, "status": result.state}
    if isinstance(result.info, dict):
        payload.update(result.info)
    if result.successful():
        payload["result"] = result.result
    elif result.failed():
        payload["error"] = str(result.result)
    return payload


@app.get("/api/jobs/{job_id}/clips/{filename}")
def get_clip(job_id: str, filename: str):
    safe_name = Path(filename).name
    path = STORAGE / job_id / safe_name
    if not path.is_file() or path.parent != STORAGE / job_id or path.suffix.lower() != ".mp4":
        raise HTTPException(status_code=404, detail="Clip not found")
    return FileResponse(path, media_type="video/mp4", filename=safe_name)



@app.get("/api/jobs/{job_id}/download")
def download_job(job_id: str):
    job_dir = STORAGE / job_id
    if not job_dir.is_dir():
        raise HTTPException(status_code=404, detail="Job not found")
    zip_path = job_dir / "shorts_bundle.zip"
    mp4_files = sorted(job_dir.glob("short_*.mp4"))
    if not mp4_files:
        raise HTTPException(status_code=404, detail="No generated Shorts available")
    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for file in mp4_files:
            archive.write(file, arcname=file.name)
    return FileResponse(zip_path, media_type="application/zip", filename=f"{job_id}-shorts.zip")



@app.post("/api/jobs/upload")
async def upload_job(
    video: UploadFile = File(...),
    clips: int = Form(10),
    min_duration: int = Form(20),
    max_duration: int = Form(60),
    caption_style: str = Form("bold"),
    remove_silence: bool = Form(True),
    background_music: bool = Form(False),
):
    if not video.filename:
        raise HTTPException(status_code=400, detail="A video file is required")
    if min_duration > max_duration:
        raise HTTPException(status_code=400, detail="min_duration must not exceed max_duration")
    allowed = {".mp4", ".mov", ".mkv", ".webm", ".m4v"}
    suffix = Path(video.filename).suffix.lower()
    if suffix not in allowed:
        raise HTTPException(status_code=400, detail="Unsupported video format")
    job_id = str(uuid4())
    job_dir = STORAGE / job_id
    job_dir.mkdir(parents=True, exist_ok=True)
    source = job_dir / f"source{suffix}"
    with source.open("wb") as output:
        while chunk := await video.read(1024 * 1024):
            output.write(chunk)
    create_shorts_job.apply_async(args=[job_id, None, clips, min_duration, max_duration, str(source), caption_style, remove_silence, background_music], task_id=job_id)
    return {"job_id": job_id, "status": "queued", "source": "upload"}
