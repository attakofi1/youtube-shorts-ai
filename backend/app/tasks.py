import json
import subprocess
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import yt_dlp
from faster_whisper import WhisperModel

from .llm_selector import select_with_llm
from .smart_crop import detect_faces
from .worker import celery_app

STORAGE = Path("/app/storage")


def download_video(url: str, output_dir: Path) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    options = {"format": "bv*[height<=1080]+ba/b[height<=1080]", "merge_output_format": "mp4", "outtmpl": str(output_dir / "source.%(ext)s"), "noplaylist": True, "quiet": True}
    with yt_dlp.YoutubeDL(options) as ydl:
        info = ydl.extract_info(url, download=True)
        return Path(ydl.prepare_filename(info)).with_suffix(".mp4")


def transcribe(video: Path):
    model = WhisperModel("small", device="cpu", compute_type="int8")
    segments, _ = model.transcribe(str(video), vad_filter=True, word_timestamps=True, condition_on_previous_text=False)
    return [{"start": float(s.start), "end": float(s.end), "text": s.text.strip(), "words": [{"start": float(w.start), "end": float(w.end), "text": w.word.strip()} for w in (s.words or [])]} for s in segments]


def _srt_time(seconds):
    ms = int(max(0, seconds) * 1000)
    h, ms = divmod(ms, 3600000)
    m, ms = divmod(ms, 60000)
    s, ms = divmod(ms, 1000)
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def make_srt(transcript, start, end, output):
    entries, number = [], 1
    for seg in transcript:
        if seg["end"] <= start or seg["start"] >= end:
            continue
        words = [w for w in seg.get("words", []) if w["end"] > start and w["start"] < end]
        for i in range(0, len(words), 6):
            group = words[i:i + 6]
            if not group:
                continue
            a = max(start, group[0]["start"]) - start
            b = min(end, group[-1]["end"]) - start
            text = " ".join(w["text"] for w in group).strip()
            if text and b > a:
                entries.append(f"{number}\n{_srt_time(a)} --> {_srt_time(b)}\n{text}\n")
                number += 1
    output.write_text("\n".join(entries), encoding="utf-8")


def _crop_filter(face_data):
    if not face_data:
        return "scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,setsar=1"
    cx = sum(x["cx"] for x in face_data) / len(face_data)
    x = f"max(0,min(iw-iw*9/16,{cx:.4f}*iw-iw*9/32))"
    return f"scale=-2:1920,crop=1080:1920:{x}:0,setsar=1"


def render_clip(source, start, end, output, srt, face_data=None):
    crop = _crop_filter(face_data)
    subtitle_path = srt.as_posix().replace("'", "\\'")
    vf = crop + ",subtitles='" + subtitle_path + "':force_style='FontName=Arial,FontSize=18,PrimaryColour=&H00FFFFFF,OutlineColour=&H00000000,BorderStyle=1,Outline=3,Shadow=1,Alignment=2,MarginV=120'"
    subprocess.run(["ffmpeg", "-y", "-ss", str(start), "-i", str(source), "-t", str(end - start), "-vf", vf, "-c:v", "libx264", "-preset", "veryfast", "-crf", "21", "-c:a", "aac", "-b:a", "128k", "-movflags", "+faststart", str(output)], check=True)


def render_one(source, transcript, clip, index, job_dir, face_data):
    srt = job_dir / f"short_{index:02d}.srt"
    output = job_dir / f"short_{index:02d}.mp4"
    make_srt(transcript, clip.start, clip.end, srt)
    local_faces = [f for f in face_data if clip.start <= f["time"] <= clip.end]
    render_clip(source, clip.start, clip.end, output, srt, local_faces)
    hook = clip.text.strip().split(". ")[0].strip()
    title = hook[:80] if hook else f"Short {index}"
    return {"start": clip.start, "end": clip.end, "text": clip.text, "score": round(clip.score, 2), "reason": clip.reason, "hook": hook, "title": title, "file": output.name, "srt": srt.name, "rank": index}


@celery_app.task(bind=True, name="create_shorts_job")
def create_shorts_job(self, job_id, url, clips, min_duration, max_duration, source_path=None):
    job_dir = STORAGE / job_id
    job_dir.mkdir(parents=True, exist_ok=True)
    source = Path(source_path) if source_path else download_video(url, job_dir)
    if not source.is_file():
        raise FileNotFoundError("Source video was not found")
    self.update_state(state="TRANSCRIBING", meta={"progress": 15, "message": "Transcribing speech with Whisper"})
    transcript = transcribe(source)
    (job_dir / "transcript.json").write_text(json.dumps(transcript, indent=2), encoding="utf-8")
    self.update_state(state="ANALYZING", meta={"progress": 30, "message": "Finding hooks, stories, questions and complete thoughts"})
    selected, selection_engine = select_with_llm(transcript, clips, min_duration, max_duration)
    face_data = detect_faces(source, sample_seconds=2.0)
    (job_dir / "face_tracking.json").write_text(json.dumps(face_data, indent=2), encoding="utf-8")
    (job_dir / "selection.json").write_text(json.dumps({"engine": selection_engine, "count": len(selected)}, indent=2), encoding="utf-8")
    self.update_state(state="RENDERING", meta={"progress": 40, "message": f"Rendering {len(selected)} Shorts in parallel"})
    manifest = []
    workers = min(4, max(1, len(selected)))
    with ThreadPoolExecutor(max_workers=workers) as executor:
        futures = {executor.submit(render_one, source, transcript, clip, index, job_dir, face_data): index for index, clip in enumerate(selected, 1)}
        done = 0
        for future in as_completed(futures):
            manifest.append(future.result())
            done += 1
            self.update_state(state="RENDERING", meta={"progress": 40 + int(55 * done / max(1, len(selected))), "message": f"Rendered {done}/{len(selected)} Shorts"})
    manifest.sort(key=lambda x: x["rank"])
    (job_dir / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    return {"job_id": job_id, "clips": manifest, "selection_engine": selection_engine, "status": "completed"}
