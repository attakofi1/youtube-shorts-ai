import os
from pathlib import Path
from dotenv import load_dotenv
load_dotenv(Path(__file__).resolve().parents[2] / ".env")

import threading
import zipfile
from uuid import uuid4
from concurrent.futures import ThreadPoolExecutor
from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field, HttpUrl
from .tasks import process_job

app = FastAPI(title="YouTube Shorts AI Windows", version="1.0.0")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"] , allow_headers=["*"])
STORAGE = Path(__file__).resolve().parents[2] / "storage"
STORAGE.mkdir(parents=True, exist_ok=True)
EXECUTOR = ThreadPoolExecutor(max_workers=2)
JOBS = {}
LOCK = threading.Lock()

class CreateJobRequest(BaseModel):
    youtube_url: HttpUrl | None = None
    clips: int = Field(10, ge=1, le=50)
    min_duration: int = Field(20, ge=10, le=120)
    max_duration: int = Field(60, ge=15, le=180)
    caption_style: str = Field("bold", pattern="^(bold|clean|karaoke)$")
    remove_silence: bool = True
    background_music: bool = False

def progress(job_id, value, message):
    with LOCK: JOBS[job_id].update({"status":"PROCESSING","progress":value,"message":message})

def run(job_id,url,clips,minimum,maximum,source,caption_style,remove_silence,background_music):
    try:
        result=process_job(job_id,url,clips,minimum,maximum,source,caption_style,remove_silence,background_music,lambda p,m:progress(job_id,p,m))
        with LOCK: JOBS[job_id].update({"status":"COMPLETED","progress":100,"message":"Completed","result":result})
    except Exception as exc:
        with LOCK: JOBS[job_id].update({"status":"FAILED","progress":100,"message":str(exc),"error":str(exc)})

@app.get("/health")
def health(): return {"status":"ok","service":"youtube-shorts-ai-windows"}

@app.post("/api/jobs")
def create_job(request:CreateJobRequest):
    if not request.youtube_url: raise HTTPException(400,"youtube_url is required")
    if request.min_duration>request.max_duration: raise HTTPException(400,"min_duration must not exceed max_duration")
    job_id=str(uuid4())
    with LOCK: JOBS[job_id]={"job_id":job_id,"status":"QUEUED","progress":0,"message":"Waiting to start"}
    EXECUTOR.submit(run,job_id,str(request.youtube_url),request.clips,request.min_duration,request.max_duration,None,request.caption_style,request.remove_silence,request.background_music)
    return {"job_id":job_id,"status":"queued"}

@app.post("/api/jobs/upload")
async def upload_job(video:UploadFile=File(...),clips:int=Form(10),min_duration:int=Form(20),max_duration:int=Form(60),caption_style:str=Form("bold"),remove_silence:bool=Form(True),background_music:bool=Form(False)):
    suffix=Path(video.filename or "").suffix.lower()
    if suffix not in {".mp4",".mov",".mkv",".webm",".m4v"}: raise HTTPException(400,"Unsupported video format")
    if min_duration>max_duration: raise HTTPException(400,"min_duration must not exceed max_duration")
    job_id=str(uuid4()); job_dir=STORAGE/job_id; job_dir.mkdir(parents=True,exist_ok=True); source=job_dir/f"source{suffix}"
    with source.open("wb") as out:
        while chunk:=await video.read(1024*1024): out.write(chunk)
    with LOCK: JOBS[job_id]={"job_id":job_id,"status":"QUEUED","progress":0,"message":"Waiting to start"}
    EXECUTOR.submit(run,job_id,None,clips,min_duration,max_duration,str(source),caption_style,remove_silence,background_music)
    return {"job_id":job_id,"status":"queued","source":"upload"}

@app.get("/api/jobs/{job_id}")
def status(job_id:str):
    with LOCK: data=JOBS.get(job_id)
    if not data: raise HTTPException(404,"Job not found")
    return data

@app.get("/api/jobs/{job_id}/clips/{filename}")
def clip(job_id:str,filename:str):
    path=STORAGE/job_id/Path(filename).name
    if not path.is_file() or path.suffix.lower()!=".mp4": raise HTTPException(404,"Clip not found")
    return FileResponse(path,media_type="video/mp4",filename=path.name)

@app.get("/api/jobs/{job_id}/thumbnails/{filename}")
def thumbnail(job_id:str,filename:str):
    path=STORAGE/job_id/Path(filename).name
    if not path.is_file() or path.suffix.lower()!=".jpg": raise HTTPException(404,"Thumbnail not found")
    return FileResponse(path,media_type="image/jpeg",filename=path.name)

@app.get("/api/jobs/{job_id}/download")
def download(job_id:str):
    folder=STORAGE/job_id; files=sorted(folder.glob("short_*.mp4"))
    if not files: raise HTTPException(404,"No generated Shorts available")
    z=folder/"shorts_bundle.zip"
    with zipfile.ZipFile(z,"w",zipfile.ZIP_DEFLATED) as archive:
        for f in files: archive.write(f,f.name)
    return FileResponse(z,media_type="application/zip",filename=f"{job_id}-shorts.zip")
