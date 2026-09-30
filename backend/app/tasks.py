import json
import os
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


def _ass_time(seconds):
    cs = int(max(0, seconds) * 100)
    h, cs = divmod(cs, 360000)
    m, cs = divmod(cs, 6000)
    s, cs = divmod(cs, 100)
    return f"{h}:{m:02d}:{s:02d}.{cs:02d}"


def make_ass(transcript, start, end, output, style="bold"):
    styles = {
        "bold": ("Arial", 18, "&H00FFFFFF", "&H00000000", 3),
        "clean": ("Arial", 16, "&H00FFFFFF", "&H66000000", 2),
        "karaoke": ("Arial", 20, "&H0000FFFF", "&H00000000", 4),
    }
    font, size, primary, outline, border = styles.get(style, styles["bold"])
    lines = [
        "[Script Info]",
        "ScriptType: v4.00+",
        "PlayResX: 1080",
        "PlayResY: 1920",
        "",
        "[V4+ Styles]",
        "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding",
        f"Style: Default,{font},{size},{primary},&H000000FF,{outline},&H99000000,-1,0,0,0,100,100,0,0,1,{border},1,2,40,40,130,1",
        "",
        "[Events]",
        "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text",
    ]
    for seg in transcript:
        if seg["end"] <= start or seg["start"] >= end:
            continue
        words = [w for w in seg.get("words", []) if w["end"] > start and w["start"] < end]
        for i in range(0, len(words), 5):
            group = words[i:i + 5]
            if not group:
                continue
            aa = max(start, group[0]["start"]) - start
            bb = min(end, group[-1]["end"]) - start
            if bb <= aa:
                continue
            if style == "karaoke":
                parts = []
                for w in group:
                    dur = max(1, int((min(end, w["end"]) - max(start, w["start"])) * 100 / 10))
                    parts.append("{\\kf" + str(dur) + "}" + w["text"].replace("{", "").replace("}", ""))
                text = " ".join(parts)
            else:
                text = " ".join(w["text"].replace("{", "").replace("}", "") for w in group)
            lines.append(f"Dialogue: 0,{_ass_time(aa)},{_ass_time(bb)},Default,,0,0,0,,{text}")
    output.write_text("\n".join(lines), encoding="utf-8")



def _crop_filter(face_data):
    if not face_data:
        return "scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,setsar=1"
    cx = sum(x["cx"] for x in face_data) / len(face_data)
    x = f"max(0,min(iw-iw*9/16,{cx:.4f}*iw-iw*9/32))"
    return f"scale=-2:1920,crop=1080:1920:{x}:0,setsar=1"


def generate_metadata(clip_text: str, rank: int):
    api_key = os.getenv("OPENAI_API_KEY")
    fallback_title = clip_text.strip().split(". ")[0].strip()[:80] or f"Short {rank}"
    fallback = {
        "title": fallback_title,
        "description": clip_text.strip()[:500],
        "hashtags": ["#shorts", "#viral", "#trending"],
    }
    if not api_key:
        return fallback, "local"
    try:
        from openai import OpenAI
        client = OpenAI(api_key=api_key)
        prompt = (
            "Create YouTube Shorts metadata. Return JSON only with title, description, hashtags. "
            "Make the title concise and curiosity-driven without misleading claims. "
            "Description should summarize the clip naturally. Return 5-8 relevant hashtags. "
            "No markdown.\\n\\nCLIP:\\n" + clip_text
        )
        response = client.responses.create(
            model=os.getenv("OPENAI_METADATA_MODEL", os.getenv("OPENAI_CLIP_MODEL", "gpt-5.6-luna")),
            input=prompt,
        )
        data = json.loads(response.output_text.strip())
        hashtags = data.get("hashtags", fallback["hashtags"])
        if isinstance(hashtags, str):
            hashtags = [x.strip() for x in hashtags.split() if x.strip()]
        return {
            "title": str(data.get("title", fallback["title"]))[:100],
            "description": str(data.get("description", fallback["description"]))[:1000],
            "hashtags": hashtags[:8],
        }, "openai"
    except Exception:
        return fallback, "local-fallback"

def render_clip(source, start, end, output, ass, face_data=None, remove_silence=True, background_music=False):
    crop = _crop_filter(face_data)
    subtitle_path = ass.as_posix().replace("'", "\\'")
    vf = crop + ",subtitles='" + subtitle_path + "'"
    audio_filter = "aresample=async=1"
    if remove_silence:
        audio_filter += ",silenceremove=stop_periods=1:stop_duration=0.6:stop_threshold=-38dB"
    music_path = os.getenv("BACKGROUND_MUSIC_PATH", "")
    if background_music and music_path and Path(music_path).is_file():
        cmd = ["ffmpeg", "-y", "-ss", str(start), "-i", str(source), "-stream_loop", "-1", "-i", music_path, "-t", str(end - start), "-vf", vf, "-filter_complex", "[0:a]aresample=async=1[a0];[1:a]volume=0.10[a1];[a0][a1]amix=inputs=2:duration=first:dropout_transition=2[aout]", "-map", "0:v:0", "-map", "[aout]", "-c:v", "libx264", "-preset", "veryfast", "-crf", "21", "-c:a", "aac", "-b:a", "128k", "-movflags", "+faststart", str(output)]
    else:
        cmd = ["ffmpeg", "-y", "-ss", str(start), "-i", str(source), "-t", str(end - start), "-vf", vf, "-af", audio_filter, "-c:v", "libx264", "-preset", "veryfast", "-crf", "21", "-c:a", "aac", "-b:a", "128k", "-movflags", "+faststart", str(output)]
    subprocess.run(cmd, check=True)


def generate_thumbnail(source, timestamp, title, output):
    safe_title = title.replace("\\", "\\\\").replace(":", "\\:").replace("'", "\\'")
    filter_text = (
        "scale=1080:1920:force_original_aspect_ratio=increase,"
        "crop=1080:1920,"
        "drawbox=x=0:y=0:w=1080:h=1920:color=black@0.25:t=fill,"
        f"drawtext=fontfile=/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf:"
        f"text='{safe_title[:70]}':fontcolor=white:fontsize=64:"
        "x=70:y=1400:box=1:boxcolor=black@0.55:boxborderw=25"
    )
    subprocess.run(["ffmpeg", "-y", "-ss", str(timestamp), "-i", str(source), "-frames:v", "1", "-vf", filter_text, str(output)], check=True)


def render_one(source, transcript, clip, index, job_dir, face_data, caption_style, remove_silence, background_music):
    ass = job_dir / f"short_{index:02d}.ass"
    output = job_dir / f"short_{index:02d}.mp4"
    make_ass(transcript, clip.start, clip.end, ass, caption_style)
    local_faces = [f for f in face_data if clip.start <= f["time"] <= clip.end]
    render_clip(source, clip.start, clip.end, output, ass, local_faces, remove_silence, background_music)
    hook = clip.text.strip().split(". ")[0].strip()
    title = hook[:80] if hook else f"Short {index}"
    metadata, metadata_engine = generate_metadata(clip.text, index)
    thumbnail = job_dir / f"short_{index:02d}.jpg"
    generate_thumbnail(source, clip.start, metadata["title"] or title, thumbnail)
    return {"start": clip.start, "end": clip.end, "text": clip.text, "score": round(clip.score, 2), "reason": clip.reason, "hook": hook, "title": metadata["title"] or title, "description": metadata["description"], "hashtags": metadata["hashtags"], "metadata_engine": metadata_engine, "file": output.name, "thumbnail": thumbnail.name, "srt": ass.name, "rank": index}


@celery_app.task(bind=True, name="create_shorts_job")
def create_shorts_job(self, job_id, url, clips, min_duration, max_duration, source_path=None, caption_style="bold", remove_silence=True, background_music=False):
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
        futures = {executor.submit(render_one, source, transcript, clip, index, job_dir, face_data, caption_style, remove_silence, background_music): index for index, clip in enumerate(selected, 1)}
        done = 0
        for future in as_completed(futures):
            manifest.append(future.result())
            done += 1
            self.update_state(state="RENDERING", meta={"progress": 40 + int(55 * done / max(1, len(selected))), "message": f"Rendered {done}/{len(selected)} Shorts"})
    manifest.sort(key=lambda x: x["rank"])
    (job_dir / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    return {"job_id": job_id, "clips": manifest, "selection_engine": selection_engine, "status": "completed"}
