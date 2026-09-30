import json
import os

from .content_ai import ClipCandidate, rank_windows


def _local(segments, count, minimum, maximum):
    return rank_windows(segments, count, minimum, maximum)


def _overlap(a, b):
    return a.start < b.end and b.start < a.end


def _non_overlapping(candidates, count):
    chosen = []
    for candidate in sorted(candidates, key=lambda x: x.score, reverse=True):
        if any(_overlap(candidate, existing) for existing in chosen):
            continue
        chosen.append(candidate)
        if len(chosen) >= count:
            break
    return sorted(chosen, key=lambda x: x.start)


def select_with_llm(segments, count, minimum, maximum):
    """
    Two-stage selector:
    1. Local ranking cheaply narrows a long transcript to strong candidates.
    2. The LLM judges only those candidates, reducing latency, context size and cost.
    """
    local_candidates = _local(segments, min(max(count * 6, 30), 80), minimum, maximum)
    if not local_candidates:
        return [], "local"

    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        return _non_overlapping(local_candidates, count), "local"

    try:
        from openai import OpenAI

        client = OpenAI(api_key=api_key)
        payload = [
            {
                "index": i,
                "start": round(c.start, 2),
                "end": round(c.end, 2),
                "text": c.text,
                "local_score": round(c.score, 2),
                "local_reason": c.reason,
            }
            for i, c in enumerate(local_candidates)
        ]
        prompt = (
            "You are selecting the strongest independent short-form video clips. "
            f"Return up to {count} clips. Every clip must be {minimum}-{maximum} seconds. "
            "Choose complete, self-contained moments with a strong hook, useful insight, "
            "surprising answer, story, joke, question-answer sequence, or memorable opinion. "
            "Avoid greetings, filler, repeated ideas, contextless fragments and abrupt endings. "
            "Do not select overlapping clips. Use only the supplied candidate timestamps. "
            "Return JSON only as an array of objects with index, score (0-100), reason, and hook.\n\n"
            "CANDIDATES:\n" + json.dumps(payload, ensure_ascii=False)
        )
        response = client.responses.create(
            model=os.getenv("OPENAI_CLIP_MODEL", "gpt-5.6-luna"),
            input=prompt,
        )
        data = json.loads(response.output_text.strip())
        selected = []
        for item in data:
            try:
                index = int(item["index"])
                candidate = local_candidates[index]
            except (KeyError, ValueError, TypeError, IndexError):
                continue
            selected.append(
                ClipCandidate(
                    candidate.start,
                    candidate.end,
                    candidate.text,
                    float(item.get("score", candidate.score)),
                    item.get("reason", "LLM selection"),
                )
            )

        selected = _non_overlapping(selected, count)
        if selected:
            return selected, "openai"
        return _non_overlapping(local_candidates, count), "local-fallback"
    except Exception:
        return _non_overlapping(local_candidates, count), "local-fallback"
