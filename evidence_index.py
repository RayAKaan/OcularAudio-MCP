"""Deterministic timestamped evidence retrieval for OcularAudio.

Phase 2 adds a local-first retrieval layer over transcript, chapter, and metadata
evidence. It deliberately avoids a model dependency: lexical relevance is stable,
fast, inspectable, and works offline once the source is cached.
"""

from __future__ import annotations

from dataclasses import dataclass
import math
import re
from typing import Any, Iterable

TOKEN_RE = re.compile(r"[\wÀ-ÖØ-öø-ÿ]+", re.UNICODE)
TIMESTAMP_RE = re.compile(r"^\[(?:(\d+):)?(\d{1,2}):(\d{2})\]\s*(.*)$")
STOPWORDS = {
    "a", "an", "and", "are", "as", "at", "be", "by", "for", "from", "how",
    "i", "in", "is", "it", "of", "on", "or", "that", "the", "this", "to",
    "was", "what", "when", "where", "which", "who", "why", "with", "you",
}


@dataclass(frozen=True)
class EvidenceSegment:
    evidence_id: str
    start_seconds: float
    end_seconds: float
    text: str
    source: str = "transcript"
    score: float = 0.0
    chapter: str = ""


def _tokens(text: str) -> list[str]:
    return [token.lower() for token in TOKEN_RE.findall(text or "") if token.lower() not in STOPWORDS]


def parse_timestamped_transcript(transcript: str) -> list[tuple[float, str]]:
    segments: list[tuple[float, str]] = []
    for raw_line in (transcript or "").splitlines():
        match = TIMESTAMP_RE.match(raw_line.strip())
        if not match:
            continue
        hours = int(match.group(1) or 0)
        minutes = int(match.group(2))
        seconds = int(match.group(3))
        text = match.group(4).strip()
        if text:
            segments.append((hours * 3600 + minutes * 60 + seconds, text))
    return segments


def build_evidence_segments(
    transcript: str,
    duration_seconds: float = 0,
    chapters: Iterable[dict[str, Any] | str] | None = None,
) -> list[EvidenceSegment]:
    parsed = parse_timestamped_transcript(transcript)
    chapter_items = _normalize_chapters(chapters)
    segments: list[EvidenceSegment] = []
    for index, (start, text) in enumerate(parsed):
        next_start = parsed[index + 1][0] if index + 1 < len(parsed) else 0
        end = max(start + 1, next_start)
        if duration_seconds:
            end = min(end, float(duration_seconds)) if end > start else end
        chapter = _chapter_for_time(start, chapter_items)
        segments.append(
            EvidenceSegment(
                evidence_id=f"e{index + 1:05d}",
                start_seconds=float(start),
                end_seconds=float(end),
                text=text,
                chapter=chapter,
            )
        )
    return segments


def _normalize_chapters(chapters: Iterable[dict[str, Any] | str] | None) -> list[tuple[float, str]]:
    result: list[tuple[float, str]] = []
    for chapter in chapters or []:
        if isinstance(chapter, dict):
            start = chapter.get("start_time", chapter.get("start", 0))
            title = str(chapter.get("title", "Untitled"))
            try:
                result.append((float(start), title))
            except (TypeError, ValueError):
                continue
        else:
            match = re.search(r"\[(?:(\d+):)?(\d{1,2}):(\d{2})\]\s*(.*)", str(chapter))
            if match:
                seconds = int(match.group(1) or 0) * 3600 + int(match.group(2)) * 60 + int(match.group(3))
                result.append((float(seconds), match.group(4).strip()))
    return sorted(result)


def _chapter_for_time(seconds: float, chapters: list[tuple[float, str]]) -> str:
    current = ""
    for start, title in chapters:
        if start > seconds:
            break
        current = title
    return current


def _score(query_tokens: list[str], query_phrase: str, segment: EvidenceSegment) -> float:
    text_tokens = _tokens(segment.text)
    if not query_tokens or not text_tokens:
        return 0.0
    text_set = set(text_tokens)
    overlap = len(set(query_tokens) & text_set)
    coverage = overlap / len(set(query_tokens))
    density = overlap / max(1, len(text_set))
    score = coverage * 5.0 + math.sqrt(density) * 2.0
    lowered = segment.text.lower()
    if query_phrase and query_phrase in lowered:
        score += 4.0
    if segment.chapter and any(token in _tokens(segment.chapter) for token in query_tokens):
        score += 1.5
    return round(score, 4)


def search_evidence(
    segments: Iterable[EvidenceSegment],
    query: str,
    top_k: int = 8,
    min_score: float = 0.0,
) -> list[EvidenceSegment]:
    query = (query or "").strip()
    if not query:
        return []
    query_tokens = _tokens(query)
    phrase = " ".join(query_tokens)
    scored: list[EvidenceSegment] = []
    for segment in segments:
        score = _score(query_tokens, phrase, segment)
        if score >= min_score:
            scored.append(
                EvidenceSegment(
                    evidence_id=segment.evidence_id,
                    start_seconds=segment.start_seconds,
                    end_seconds=segment.end_seconds,
                    text=segment.text,
                    source=segment.source,
                    score=score,
                    chapter=segment.chapter,
                )
            )
    scored.sort(key=lambda item: (-item.score, item.start_seconds))
    return scored[: max(1, min(int(top_k), 50))]


def timeline_window(
    segments: list[EvidenceSegment],
    start_seconds: float = 0,
    end_seconds: float | None = None,
) -> list[EvidenceSegment]:
    end = float("inf") if end_seconds is None else float(end_seconds)
    start = max(0.0, float(start_seconds))
    return [
        segment for segment in segments
        if segment.end_seconds >= start and segment.start_seconds <= end
    ]


def nearest_evidence(segments: list[EvidenceSegment], timestamp_seconds: float) -> EvidenceSegment | None:
    if not segments:
        return None
    target = float(timestamp_seconds)
    return min(
        segments,
        key=lambda item: 0 if item.start_seconds <= target <= item.end_seconds
        else min(abs(item.start_seconds - target), abs(item.end_seconds - target)),
    )


def format_timestamp(seconds: float) -> str:
    total = max(0, int(seconds))
    hours, remainder = divmod(total, 3600)
    minutes, secs = divmod(remainder, 60)
    return f"[{hours:02d}:{minutes:02d}:{secs:02d}]" if hours else f"[{minutes:02d}:{secs:02d}]"
