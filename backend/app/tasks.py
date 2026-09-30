import json
import re
import subprocess
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import yt_dlp
from faster_whisper import WhisperModel

from .smart_crop import detect_faces
from .worker import celery_app

STORAGE = Path("/app/storage")
HOOK_WORDS = {"secret", "mistake", "never", "best", "worst", "truth", "why", "how", "important", "problem", "solution", "money", "success", "failure", "learn", "warning", "remember", "first", "only", "because", "surprising", "wrong", "crazy", "impossible", "nobody", "everyone"}


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


def _score_window(window):
    text = " ".join(x["text"] for x in window).lower()
    words = re.findall(r"\b\w+\b", text)
    if not words:
        return -1
    keyword_hits = sum(1 for word in words if word in HOOK_WORDS)
    question_hits = text.count("?")
    exclamation_hits = text.count("!")
    density = len(words) / max(1, window[-1]["end"] - window[0]["start"])
    opening = min(1.0, len(words) / 18)
    return keyword_hits * 2.5 + question_hits * 1.5 + exclamation_hits + min(density, 4) * 2 + opening * 2


def choose_segments(segments, count, min_duration, max_duration):
    candidates = []
    for i, start_seg in enumerate(segments):
        window = []
        for seg in segments[i:]:
            window.append(seg)
            duration = seg["end"] - start_seg["start"]
            if duration >= min_duration:
                if duration > max_duration:
                    break
                score = _score_window(window)
                candidates.append({"start": start_seg["start"], "end": seg["end"], "text": " ".join(x["text"] for x in window), "score": round(score, 3)})
                break
    candidates.sort(key=lambda x: x["score"], reverse=True)
    selected = []
    for candidate in candidates:
        overlap = any(max(candidate["start"], item["start"]) < min(candidate["end"], item["end"]) * 0.65 for item in selected)
        if not overlap:
            selected.append(candidate)
        if len(selected) >= count:
            break
    return selected


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
    # Use a stable center from detected faces. This avoids violent camera movement.
    cx = sum(x["cx"] for x in face_data) / len(face_data)
    # iw/ih is evaluated by FFmpeg. The expression keeps the subject around the center.
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
    make_srt(transcript, clip["start"], clip["end"], srt)
    local_faces = [f for f in face_data if clip["start"] <= f["time"] <= clip["end"]]
    render_clip(source, clip["start"], clip["end"], output, srt, local_faces)
    return {**clip, "file": output.name, "srt": srt.name, "rank": index}


@celery_app.task(bind=True, name="create_shorts_job")
def create_shorts_job(self, job_id, url, clips, min_duration, max_duration):
    job_dir = STORAGE / job_id
    job_dir.mkdir(parents=True, exist_ok=True)
    source = download_video(url, job_dir)
    self.update_state(state="TRANSCRIBING", meta={"progress": 15, "message": "Transcribing audio"})
    transcript = transcribe(source)
    (job_dir / "transcript.json").write_text(json.dumps(transcript, indent=2), encoding="utf-8")
    self.update_state(state="ANALYZING", meta={"progress": 30, "message": "Analyzing moments and tracking speakers"})
    selected = choose_segments(transcript, clips, min_duration, max_duration)
    face_data = detect_faces(source, sample_seconds=2.0)
    (job_dir / "face_tracking.json").write_text(json.dumps(face_data, indent=2), encoding="utf-8")
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
    return {"job_id": job_id, "clips": manifest, "status": "completed"}
