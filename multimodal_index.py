"""Multimodal evidence alignment for OcularAudio.

Phase 5 connects transcript, OCR, and visual frame evidence into timestamped
moments. It does not claim model-generated vision reasoning: all signals are
deterministic and inspectable, making the layer reliable and replaceable.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
import re
from typing import Any, Iterable

from evidence_index import EvidenceSegment, nearest_evidence, timeline_window
from visual_index import VisualFrame, hamming_distance

TOKEN_RE = re.compile(r"[\wÀ-ÖØ-öø-ÿ]+", re.UNICODE)


@dataclass(frozen=True)
class MultimodalMoment:
    moment_id: str
    timestamp_seconds: float
    start_seconds: float
    end_seconds: float
    transcript: list[dict[str, Any]]
    visual_frames: list[dict[str, Any]]
    ocr_text: str
    visual_change_score: float
    evidence_score: float
    modalities: list[str]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _frame_payload(frame: VisualFrame) -> dict[str, Any]:
    return {
        "frame_id": frame.frame_id,
        "timestamp_seconds": frame.timestamp_seconds,
        "image_path": frame.image_path,
        "width": frame.width,
        "height": frame.height,
        "brightness": frame.brightness,
        "contrast": frame.contrast,
        "phash": frame.phash,
        "ocr_text": frame.ocr_text,
    }


def _evidence_payload(segment: EvidenceSegment) -> dict[str, Any]:
    return {
        "evidence_id": segment.evidence_id,
        "start_seconds": segment.start_seconds,
        "end_seconds": segment.end_seconds,
        "text": segment.text,
        "chapter": segment.chapter,
        "source": segment.source,
        "score": segment.score,
    }


def visual_change_score(previous: VisualFrame | None, current: VisualFrame) -> float:
    if previous is None:
        return 0.0
    distance = hamming_distance(previous.phash, current.phash)
    return round(min(1.0, distance / max(1, len(current.phash))), 6)


def build_multimodal_moments(
    transcript_segments: Iterable[EvidenceSegment],
    visual_frames: Iterable[VisualFrame],
    window_seconds: float = 5,
) -> list[MultimodalMoment]:
    segments = sorted(list(transcript_segments), key=lambda item: item.start_seconds)
    frames = sorted(list(visual_frames), key=lambda item: item.timestamp_seconds)
    if not frames and not segments:
        return []

    moments: list[MultimodalMoment] = []
    previous: VisualFrame | None = None
    for index, frame in enumerate(frames, 1):
        timestamp = frame.timestamp_seconds
        nearby = timeline_window(
            segments,
            max(0.0, timestamp - max(0.0, window_seconds)),
            timestamp + max(0.0, window_seconds),
        )
        nearest = nearest_evidence(segments, timestamp)
        if nearest and nearest not in nearby:
            nearby = sorted(nearby + [nearest], key=lambda item: item.start_seconds)

        ocr = (frame.ocr_text or "").strip()
        transcript_score = max((item.score for item in nearby), default=0.0)
        change = visual_change_score(previous, frame)
        modalities = ["visual"]
        if nearby:
            modalities.append("transcript")
        if ocr:
            modalities.append("ocr")

        moments.append(
            MultimodalMoment(
                moment_id=f"m{index:05d}",
                timestamp_seconds=timestamp,
                start_seconds=max(0.0, timestamp - window_seconds),
                end_seconds=timestamp + window_seconds,
                transcript=[_evidence_payload(item) for item in nearby],
                visual_frames=[_frame_payload(frame)],
                ocr_text=ocr,
                visual_change_score=change,
                evidence_score=round(min(1.0, transcript_score / 10.0), 6),
                modalities=modalities,
            )
        )
        previous = frame

    # If no visual frames exist, preserve transcript evidence as multimodal-ready moments.
    if not frames:
        for index, segment in enumerate(segments, 1):
            moments.append(
                MultimodalMoment(
                    moment_id=f"m{index:05d}",
                    timestamp_seconds=segment.start_seconds,
                    start_seconds=segment.start_seconds,
                    end_seconds=segment.end_seconds,
                    transcript=[_evidence_payload(segment)],
                    visual_frames=[],
                    ocr_text="",
                    visual_change_score=0.0,
                    evidence_score=round(min(1.0, max(0.0, segment.score) / 10.0), 6),
                    modalities=["transcript"],
                )
            )
    return moments


def rank_multimodal_moments(
    moments: Iterable[MultimodalMoment],
    query: str = "",
    top_k: int = 8,
) -> list[MultimodalMoment]:
    query_tokens = {token.lower() for token in TOKEN_RE.findall(query or "")}
    scored: list[tuple[float, MultimodalMoment]] = []
    for moment in moments:
        text = " ".join(
            [item["text"] for item in moment.transcript]
            + [moment.ocr_text]
        ).lower()
        overlap = len(query_tokens & {token.lower() for token in TOKEN_RE.findall(text)})
        query_score = overlap / len(query_tokens) if query_tokens else 0.0
        signal_score = (
            query_score * 0.55
            + moment.evidence_score * 0.2
            + moment.visual_change_score * 0.25
        )
        scored.append((signal_score, moment))
    scored.sort(key=lambda item: (-item[0], item[1].timestamp_seconds, item[1].moment_id))
    return [moment for _, moment in scored[:max(1, min(int(top_k), 50))]]


def describe_moment(moment: MultimodalMoment) -> dict[str, Any]:
    visual_signal = "stable"
    if moment.visual_change_score >= 0.55:
        visual_signal = "major_visual_change"
    elif moment.visual_change_score >= 0.25:
        visual_signal = "visual_change"

    return {
        "moment_id": moment.moment_id,
        "timestamp_seconds": moment.timestamp_seconds,
        "timestamp": _format_timestamp(moment.timestamp_seconds),
        "window": {
            "start_seconds": moment.start_seconds,
            "end_seconds": moment.end_seconds,
        },
        "modalities": moment.modalities,
        "visual_signal": visual_signal,
        "visual_change_score": moment.visual_change_score,
        "evidence_score": moment.evidence_score,
        "transcript": moment.transcript,
        "ocr_text": moment.ocr_text,
        "visual_frames": moment.visual_frames,
    }


def _format_timestamp(seconds: float) -> str:
    total = max(0, int(seconds))
    minutes, secs = divmod(total, 60)
    hours, minutes = divmod(minutes, 60)
    return f"[{hours:02d}:{minutes:02d}:{secs:02d}]" if hours else f"[{minutes:02d}:{secs:02d}]"
