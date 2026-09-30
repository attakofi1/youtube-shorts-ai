import json
import subprocess
from pathlib import Path


def detect_faces(video: Path, sample_seconds: float = 0.75):
    """Best-effort face tracking using OpenCV Haar cascade when available.

    Returns timestamped face centers. If OpenCV is unavailable, returns an empty
    list and the renderer falls back to center cropping.
    """
    try:
        import cv2
    except ImportError:
        return []

    cap = cv2.VideoCapture(str(video))
    fps = cap.get(cv2.CAP_PROP_FPS) or 30
    frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
    duration = frames / fps if fps else 0
    cascade = cv2.CascadeClassifier(cv2.data.haarcascades + "haarcascade_frontalface_default.xml")
    results = []
    t = 0.0
    smooth_x = None
    smooth_y = None
    while t < duration:
        cap.set(cv2.CAP_PROP_POS_MSEC, t * 1000)
        ok, frame = cap.read()
        if not ok:
            break
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        faces = cascade.detectMultiScale(gray, scaleFactor=1.1, minNeighbors=5, minSize=(60, 60))
        if len(faces):
            x, y, w, h = max(faces, key=lambda f: f[2] * f[3])
            raw_x = (x + w / 2) / frame.shape[1]
            raw_y = (y + h / 2) / frame.shape[0]
            smooth_x = raw_x if smooth_x is None else (0.35 * raw_x + 0.65 * smooth_x)
            smooth_y = raw_y if smooth_y is None else (0.35 * raw_y + 0.65 * smooth_y)
            results.append({"time": t, "cx": smooth_x, "cy": smooth_y, "area": (w * h) / (frame.shape[1] * frame.shape[0])})
        t += sample_seconds
    cap.release()
    return results


def save_tracking(video: Path, output: Path):
    output.write_text(json.dumps(detect_faces(video), indent=2), encoding="utf-8")
