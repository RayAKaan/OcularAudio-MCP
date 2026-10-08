"""Deterministic visual evidence indexing for OcularAudio.

Phase 3 turns captured frames into persistent, timestamp-addressable evidence.
The index is deliberately local-first: perceptual hashes, image statistics, and
optional OCR make visual evidence inspectable without requiring a vision model.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
import math
import re
from typing import Any, Iterable

import cv2
import numpy as np

TOKEN_RE = re.compile(r"[\wÀ-ÖØ-öø-ÿ]+", re.UNICODE)


@dataclass(frozen=True)
class VisualFrame:
    frame_id: str
    timestamp_seconds: float
    image_path: str
    width: int
    height: int
    brightness: float
    contrast: float
    phash: str
    ocr_text: str = ""
    score: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _tokens(text: str) -> list[str]:
    return [token.lower() for token in TOKEN_RE.findall(text or "")]


def select_burst_timestamps(
    center_seconds: float,
    radius_seconds: float = 10,
    count: int = 5,
    duration_seconds: float | None = None,
) -> list[int]:
    count = max(1, min(int(count), 31))
    radius = max(0.0, float(radius_seconds))
    center = max(0.0, float(center_seconds))
    if count == 1 or radius == 0:
        values = [center]
    else:
        step = (2 * radius) / (count - 1)
        values = [center - radius + step * index for index in range(count)]
    result = sorted({max(0, int(round(value))) for value in values})
    if duration_seconds is not None:
        result = [value for value in result if value <= max(0, int(duration_seconds))]
    return result


def sample_timestamps(
    duration_seconds: float,
    interval_seconds: float = 10,
    max_frames: int = 240,
) -> list[int]:
    duration = max(0.0, float(duration_seconds))
    interval = max(1.0, float(interval_seconds))
    limit = max(1, min(int(max_frames), 1000))
    if duration == 0:
        return [0]
    values = list(range(0, max(1, int(math.floor(duration))) + 1, int(interval)))
    if int(duration) not in values:
        values.append(int(duration))
    return sorted(set(values))[:limit]


def normalize_crop_box(
    x: float,
    y: float,
    width: float,
    height: float,
    frame_width: int,
    frame_height: int,
    normalized: bool = True,
) -> tuple[int, int, int, int]:
    if normalized:
        left = int(round(float(x) * frame_width))
        top = int(round(float(y) * frame_height))
        right = int(round((float(x) + float(width)) * frame_width))
        bottom = int(round((float(y) + float(height)) * frame_height))
    else:
        left = int(round(x))
        top = int(round(y))
        right = int(round(x + width))
        bottom = int(round(y + height))
    left = max(0, min(left, frame_width - 1))
    top = max(0, min(top, frame_height - 1))
    right = max(left + 1, min(right, frame_width))
    bottom = max(top + 1, min(bottom, frame_height))
    return left, top, right, bottom


def perceptual_hash(image: np.ndarray) -> str:
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY) if image.ndim == 3 else image
    resized = cv2.resize(gray, (32, 32), interpolation=cv2.INTER_AREA).astype(np.float32)
    dct = cv2.dct(resized)
    low = dct[:8, :8]
    threshold = float(np.median(low[1:, :]))
    bits = (low > threshold).astype(np.uint8).flatten()
    return "".join("1" if bit else "0" for bit in bits)


def hamming_distance(first: str, second: str) -> int:
    if len(first) != len(second):
        return max(len(first), len(second))
    return sum(a != b for a, b in zip(first, second))


def frame_descriptor(
    image_path: str,
    timestamp_seconds: float,
    frame_id: str,
    ocr_text: str = "",
) -> VisualFrame:
    image = cv2.imread(image_path)
    if image is None:
        raise ValueError(f"Unable to read frame: {image_path}")
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    return VisualFrame(
        frame_id=frame_id,
        timestamp_seconds=float(timestamp_seconds),
        image_path=image_path,
        width=int(image.shape[1]),
        height=int(image.shape[0]),
        brightness=round(float(np.mean(gray)), 3),
        contrast=round(float(np.std(gray)), 3),
        phash=perceptual_hash(image),
        ocr_text=(ocr_text or "").strip(),
    )


def search_visual_frames(
    frames: Iterable[VisualFrame],
    query: str,
    top_k: int = 8,
    min_score: float = 0.0,
) -> list[VisualFrame]:
    query = (query or "").strip().lower()
    query_tokens = set(_tokens(query))
    if not query_tokens:
        return []
    scored: list[VisualFrame] = []
    for frame in frames:
        text = (frame.ocr_text or "").lower()
        tokens = set(_tokens(text))
        overlap = len(query_tokens & tokens)
        score = overlap / len(query_tokens) * 5.0
        if query and query in text:
            score += 4.0
        if overlap and text:
            score += min(1.0, overlap / max(1, len(tokens)))
        if score >= min_score:
            scored.append(
                VisualFrame(**{**frame.to_dict(), "score": round(score, 4)})
            )
    scored.sort(key=lambda item: (-item.score, item.timestamp_seconds, item.frame_id))
    return scored[: max(1, min(int(top_k), 50))]


def frames_from_payload(payload: Iterable[dict[str, Any]]) -> list[VisualFrame]:
    frames: list[VisualFrame] = []
    for item in payload:
        try:
            frames.append(VisualFrame(**item))
        except (TypeError, ValueError):
            continue
    return frames
