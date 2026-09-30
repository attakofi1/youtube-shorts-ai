"""Local semantic clip analysis.

This module ranks transcript windows using conversational structure rather than
only isolated keywords. It is deliberately dependency-light so the worker
remains fast and usable without an external LLM API.
"""
import re
from dataclasses import dataclass


HOOKS = {
    "secret", "mistake", "truth", "warning", "surprising", "shocking", "crazy",
    "impossible", "nobody", "everyone", "never", "always", "first", "only",
    "because", "problem", "solution", "money", "success", "failure", "wrong",
    "learn", "lesson", "reason", "important", "actually", "finally", "best",
    "worst", "hidden", "forgot", "realize", "story", "happened"
}

TRANSITIONS = {
    "but", "however", "because", "so", "then", "until", "when", "after", "before",
    "instead", "although", "except", "finally", "that's why", "the reason"
}


@dataclass
class ClipCandidate:
    start: float
    end: float
    text: str
    score: float
    reason: str


def _words(text: str):
    return re.findall(r"[a-zA-Z0-9']+", text.lower())


def _score(text: str, duration: float, start_text: str = ""):
    words = _words(text)
    if not words:
        return -999, "empty"
    lower = text.lower()
    hooks = sum(w in HOOKS for w in words)
    questions = text.count("?")
    exclamations = text.count("!")
    transitions = sum(t in lower for t in TRANSITIONS)
    density = len(words) / max(duration, 1)
    first_sentence = start_text.strip().lower()
    hook_open = any(w in _words(first_sentence) for w in HOOKS)
    story_signal = transitions + sum(x in lower for x in ("first", "then", "after that", "finally"))
    score = hooks * 2.2 + questions * 1.8 + exclamations * 1.0 + transitions * 1.5
    score += min(density, 3.5) * 1.8 + story_signal * 1.2 + (3.0 if hook_open else 0)
    score -= max(0, 0.7 - density) * 5
    reasons = []
    if hook_open: reasons.append("strong opening")
    if questions: reasons.append("question")
    if hooks: reasons.append("hook language")
    if story_signal >= 2: reasons.append("story structure")
    if transitions: reasons.append("complete thought")
    return score, ", ".join(reasons) or "high speech density"


def rank_windows(segments, count, min_duration, max_duration):
    candidates = []
    for i, start in enumerate(segments):
        window = []
        for end_seg in segments[i:]:
            window.append(end_seg)
            duration = end_seg["end"] - start["start"]
            if duration < min_duration:
                continue
            if duration > max_duration:
                break
            text = " ".join(x["text"] for x in window).strip()
            score, reason = _score(text, duration, start["text"])
            candidates.append(ClipCandidate(start["start"], end_seg["end"], text, score, reason))
            break
    candidates.sort(key=lambda c: c.score, reverse=True)
    chosen = []
    for candidate in candidates:
        overlap = False
        for existing in chosen:
            intersection = max(0.0, min(candidate.end, existing.end) - max(candidate.start, existing.start))
            shortest = min(candidate.end - candidate.start, existing.end - existing.start)
            if shortest and intersection / shortest > 0.35:
                overlap = True
                break
        if not overlap:
            chosen.append(candidate)
        if len(chosen) >= count:
            break
    return chosen
