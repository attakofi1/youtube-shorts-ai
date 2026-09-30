import json
import os
from typing import Any

from .content_ai import ClipCandidate, rank_windows


def _local(segments, count, minimum, maximum):
    return rank_windows(segments, count, minimum, maximum)


def select_with_llm(segments, count, minimum, maximum):
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        return _local(segments, count, minimum, maximum), "local"

    try:
        from openai import OpenAI
        client = OpenAI(api_key=api_key)
        payload = [
            {"index": i, "start": s["start"], "end": s["end"], "text": s["text"]}
            for i, s in enumerate(segments)
        ]
        prompt = (
            "You select clips from a long-form video for vertical short-form content. "
            f"Return up to {count} non-overlapping clips, each {minimum}-{maximum} seconds. "
            "Prefer complete stories, surprising answers, useful explanations, jokes, strong opinions, "
            "questions followed by answers, and moments with a strong hook. Avoid greetings, filler, "
            "contextless fragments, repeated points, and abrupt endings. "
            "Return JSON only as an array of objects with start, end, score (0-100), reason, and hook. "
            "Use timestamps from the supplied transcript segments.\n\nTRANSCRIPT:\n" + json.dumps(payload, ensure_ascii=False)
        )
        response = client.responses.create(
            model=os.getenv("OPENAI_CLIP_MODEL", "gpt-5.6-luna"),
            input=prompt,
        )
        raw = response.output_text.strip()
        data = json.loads(raw)
        selected = []
        for item in data:
            start, end = float(item["start"]), float(item["end"])
            if end <= start or end - start < minimum or end - start > maximum:
                continue
            text = " ".join(s["text"] for s in segments if s["end"] > start and s["start"] < end).strip()
            selected.append(ClipCandidate(start, end, text, float(item.get("score", 0)), item.get("reason", "LLM selection")))
        selected.sort(key=lambda x: x.score, reverse=True)
        return selected[:count], "openai"
    except Exception:
        return _local(segments, count, minimum, maximum), "local-fallback"
