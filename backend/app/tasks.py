import json
import subprocess
from pathlib import Path

import yt_dlp
from faster_whisper import WhisperModel

from .worker import celery_app

STORAGE = Path("/app/storage")


def download_video(url: str, output_dir: Path) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    options = {
        "format": "bv*[height<=1080]+ba/b[height<=1080]",
        "merge_output_format": "mp4",
        "outtmpl": str(output_dir / "source.%(ext)s"),
        "noplaylist": True,
        "quiet": True,
    }
    with yt_dlp.YoutubeDL(options) as ydl:
        info = ydl.extract_info(url, download=True)
        path = Path(ydl.prepare_filename(info)).with_suffix(".mp4")
    return path


def transcribe(video: Path):
    model = WhisperModel("small", device="cpu", compute_type="int8")
    segments, info = model.transcribe(str(video), vad_filter=True, word_timestamps=True)
    return [
        {
            "start": float(s.start),
            "end": float(s.end),
            "text": s.text.strip(),
        }
        for s in segments
    ]


def choose_segments(segments, count, min_duration, max_duration):
    if not segments:
        return []
    candidates = []
    start = segments[0]["start"]
    text = []
    for seg in segments:
        text.append(seg["text"])
        duration = seg["end"] - start
        if duration >= min_duration:
            candidates.append({"start": start, "end": seg["end"], "text": " ".join(text)})
        if duration >= max_duration:
            start = seg["end"]
            text = []
    candidates = candidates[-count:]
    return candidates


def render_clip(source, start, end, output):
    vf = (
        "scale=1080:1920:force_original_aspect_ratio=increase,"
        "crop=1080:1920,setsar=1"
    )
    subprocess.run([
        "ffmpeg", "-y", "-ss", str(start), "-i", str(source),
        "-t", str(end - start), "-vf", vf,
        "-c:v", "libx264", "-preset", "veryfast", "-crf", "21",
        "-c:a", "aac", "-b:a", "128k", "-movflags", "+faststart", str(output)
    ], check=True)


@celery_app.task(bind=True, name="create_shorts_job")
def create_shorts_job(self, job_id, url, clips, min_duration, max_duration):
    job_dir = STORAGE / job_id
    job_dir.mkdir(parents=True, exist_ok=True)
    source = download_video(url, job_dir)
    self.update_state(state="TRANSCRIBING", meta={"progress": 20})
    transcript = transcribe(source)
    (job_dir / "transcript.json").write_text(json.dumps(transcript, indent=2), encoding="utf-8")
    self.update_state(state="SELECTING", meta={"progress": 40})
    selected = choose_segments(transcript, clips, min_duration, max_duration)
    manifest = []
    for index, clip in enumerate(selected, 1):
        output = job_dir / f"short_{index:02d}.mp4"
        render_clip(source, clip["start"], clip["end"], output)
        manifest.append({**clip, "file": output.name})
        self.update_state(state="RENDERING", meta={"progress": 40 + int(55 * index / max(1, len(selected)))})
    (job_dir / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    return {"job_id": job_id, "clips": manifest, "status": "completed"}
