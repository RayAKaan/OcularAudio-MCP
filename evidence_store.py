"""Canonical, provenance-preserving evidence records and local manifest storage.

The store is a deterministic projection of transcript, chapter, metadata, visual,
and OCR caches. Stable IDs and atomic manifests let every retrieval layer refer to
the same evidence without requiring a database or external service.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
import hashlib
import json
import math
import os
from pathlib import Path
import re
import tempfile
import threading
from typing import Any, Iterable

from evidence_index import build_evidence_segments

SCHEMA_VERSION = 1
ALLOWED_MODALITIES = frozenset({"transcript", "visual", "ocr", "chapter", "metadata"})
SOURCE_ID_RE = re.compile(r"^[A-Za-z0-9_-]{1,128}$")
TIMESTAMP_RE = re.compile(r"\[(?:(\d+):)?(\d{1,2}):(\d{2})\]")
MAX_RECORDS_PER_SOURCE = 100_000
_STORE_LOCK = threading.RLock()


@dataclass(frozen=True)
class EvidenceRecord:
    evidence_id: str
    source_id: str
    modality: str
    start_seconds: float
    end_seconds: float
    text: str
    content_hash: str
    provenance: dict[str, Any]
    metadata: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "EvidenceRecord":
        if not isinstance(payload, dict):
            raise ValueError("Evidence record must be an object.")
        record = cls(
            evidence_id=str(payload.get("evidence_id", "")),
            source_id=str(payload.get("source_id", "")),
            modality=str(payload.get("modality", "")),
            start_seconds=payload.get("start_seconds", 0),
            end_seconds=payload.get("end_seconds", 0),
            text=str(payload.get("text", "")),
            content_hash=str(payload.get("content_hash", "")),
            provenance=payload.get("provenance") if isinstance(payload.get("provenance"), dict) else {},
            metadata=payload.get("metadata") if isinstance(payload.get("metadata"), dict) else {},
        )
        validate_record(record)
        return record


def _canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)


def _text_hash(text: str) -> str:
    return hashlib.sha256(text.strip().encode("utf-8")).hexdigest()


def _stable_id(
    source_id: str,
    modality: str,
    start_seconds: float,
    end_seconds: float,
    text: str,
    locator: str = "",
) -> str:
    identity = {
        "source_id": source_id,
        "modality": modality,
        "start_ms": round(float(start_seconds) * 1000),
        "end_ms": round(float(end_seconds) * 1000),
        "text": " ".join(text.split()),
        "locator": locator,
    }
    digest = hashlib.sha256(_canonical_json(identity).encode("utf-8")).hexdigest()[:32]
    return "ev_" + digest


def validate_record(record: EvidenceRecord) -> None:
    if not SOURCE_ID_RE.fullmatch(record.source_id):
        raise ValueError("source_id must be a safe 1-128 character identifier.")
    if not record.evidence_id.startswith("ev_") or len(record.evidence_id) != 35:
        raise ValueError("evidence_id must be a stable ev_ identifier.")
    if record.modality not in ALLOWED_MODALITIES:
        raise ValueError(f"Unsupported evidence modality: {record.modality!r}.")
    if not math.isfinite(float(record.start_seconds)) or not math.isfinite(float(record.end_seconds)):
        raise ValueError("Evidence timestamps must be finite.")
    if float(record.start_seconds) < 0 or float(record.end_seconds) < float(record.start_seconds):
        raise ValueError("Evidence timestamps must be non-negative and end >= start.")
    if not record.text.strip():
        raise ValueError("Evidence text must not be empty.")
    if record.content_hash != _text_hash(record.text):
        raise ValueError("Evidence content hash does not match its text.")
    if not isinstance(record.provenance, dict) or not isinstance(record.metadata, dict):
        raise ValueError("Evidence provenance and metadata must be objects.")


def _make_record(
    source_id: str,
    modality: str,
    start_seconds: float,
    end_seconds: float,
    text: str,
    *,
    locator: str = "",
    provenance: dict[str, Any] | None = None,
    metadata: dict[str, Any] | None = None,
) -> EvidenceRecord | None:
    clean_text = " ".join(str(text or "").split())
    if not clean_text:
        return None
    start = float(start_seconds)
    end = float(end_seconds)
    record = EvidenceRecord(
        evidence_id=_stable_id(source_id, modality, start, end, clean_text, locator),
        source_id=source_id,
        modality=modality,
        start_seconds=round(start, 3),
        end_seconds=round(max(start, end), 3),
        text=clean_text,
        content_hash=_text_hash(clean_text),
        provenance=dict(provenance or {}),
        metadata=dict(metadata or {}),
    )
    validate_record(record)
    return record


def _chapter_fields(chapter: Any) -> tuple[float, str] | None:
    if isinstance(chapter, dict):
        try:
            start = float(chapter.get("start_time", chapter.get("start", 0)) or 0)
        except (TypeError, ValueError):
            return None
        title = str(chapter.get("title", "")).strip()
        return (start, title) if math.isfinite(start) and start >= 0 and title else None
    raw = str(chapter or "")
    match = TIMESTAMP_RE.search(raw)
    if not match:
        return None
    hours = int(match.group(1) or 0)
    minutes = int(match.group(2))
    seconds = int(match.group(3))
    title = raw[match.end():].strip(" :-•\t")
    if not title:
        return None
    return float(hours * 3600 + minutes * 60 + seconds), title


def build_canonical_evidence(
    source_id: str,
    transcript: str = "",
    duration_seconds: float = 0,
    chapters: Iterable[Any] | None = None,
    visual_frames: Iterable[dict[str, Any]] | None = None,
    source_metadata: dict[str, Any] | None = None,
) -> list[EvidenceRecord]:
    """Normalize cached source artifacts into stable, typed, deduplicated records."""
    if not SOURCE_ID_RE.fullmatch(str(source_id or "")):
        raise ValueError("source_id must be a safe 1-128 character identifier.")
    try:
        duration = float(duration_seconds or 0)
    except (TypeError, ValueError):
        duration = 0.0
    if not math.isfinite(duration) or duration < 0:
        duration = 0.0

    chapter_values = list(chapters or [])
    records: dict[str, EvidenceRecord] = {}
    for segment in build_evidence_segments(transcript or "", duration_seconds=duration, chapters=chapter_values):
        if duration and segment.start_seconds > duration:
            continue
        record = _make_record(
            source_id, "transcript", segment.start_seconds, segment.end_seconds, segment.text,
            locator=f"transcript:{round(segment.start_seconds * 1000)}",
            provenance={"artifact": "transcript_cache", "legacy_segment_id": segment.evidence_id},
            metadata={"chapter": segment.chapter},
        )
        if record:
            records[record.evidence_id] = record

    normalized_chapters = []
    for index, chapter in enumerate(chapter_values):
        fields = _chapter_fields(chapter)
        if not fields:
            continue
        start, title = fields
        normalized_chapters.append((start, title, index))
    for start, title, index in normalized_chapters:
        record = _make_record(
            source_id, "chapter", start, start, title,
            locator=f"chapter:{index}:{round(start * 1000)}",
            provenance={"artifact": "source_metadata", "chapter_index": index},
        )
        if record:
            records[record.evidence_id] = record

    metadata = source_metadata if isinstance(source_metadata, dict) else {}
    title = str(metadata.get("title", "")).strip()
    if title:
        record = _make_record(
            source_id, "metadata", 0, 0, title,
            locator="metadata:title",
            provenance={"artifact": "transcript_cache", "field": "title"},
            metadata={"field": "title"},
        )
        if record:
            records[record.evidence_id] = record

    for index, frame in enumerate(visual_frames or []):
        if not isinstance(frame, dict):
            continue
        try:
            timestamp = float(frame.get("timestamp_seconds", 0) or 0)
        except (TypeError, ValueError):
            continue
        if not math.isfinite(timestamp) or timestamp < 0:
            continue
        frame_id = str(frame.get("frame_id", f"frame-{index}"))
        frame_metadata = {
            key: frame.get(key)
            for key in ("width", "height", "brightness", "contrast", "phash", "image_path")
            if frame.get(key) is not None
        }
        visual_text = str(frame.get("description", "")).strip() or f"Visual frame at {timestamp:g} seconds"
        visual = _make_record(
            source_id, "visual", timestamp, timestamp, visual_text,
            locator=frame_id + ":" + str(frame.get("phash", "")),
            provenance={"artifact": "visual_index", "frame_id": frame_id},
            metadata=frame_metadata,
        )
        if visual:
            records[visual.evidence_id] = visual
        ocr_text = str(frame.get("ocr_text", "")).strip()
        ocr = _make_record(
            source_id, "ocr", timestamp, timestamp, ocr_text,
            locator=frame_id,
            provenance={"artifact": "visual_index", "frame_id": frame_id},
            metadata=frame_metadata,
        )
        if ocr:
            records[ocr.evidence_id] = ocr

    result = sorted(records.values(), key=lambda item: (item.start_seconds, item.modality, item.evidence_id))
    if len(result) > MAX_RECORDS_PER_SOURCE:
        raise ValueError(f"Evidence record limit exceeded ({MAX_RECORDS_PER_SOURCE}).")
    return result


class EvidenceStore:
    """Atomic per-source JSON manifests with schema and content-integrity checks."""

    def __init__(self, directory: str | Path):
        self.directory = Path(directory)
        self.directory.mkdir(parents=True, exist_ok=True)

    def _path(self, source_id: str) -> Path:
        if not SOURCE_ID_RE.fullmatch(str(source_id or "")):
            raise ValueError("source_id must be a safe 1-128 character identifier.")
        return self.directory / f"{source_id}.json"

    def save(
        self,
        source_id: str,
        records: Iterable[EvidenceRecord],
        source_metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        target = self._path(source_id)
        normalized: dict[str, EvidenceRecord] = {}
        for item in records:
            record = item if isinstance(item, EvidenceRecord) else EvidenceRecord.from_dict(item)
            validate_record(record)
            if record.source_id != source_id:
                raise ValueError("Every record must belong to the manifest source_id.")
            normalized[record.evidence_id] = record
        if len(normalized) > MAX_RECORDS_PER_SOURCE:
            raise ValueError(f"Evidence record limit exceeded ({MAX_RECORDS_PER_SOURCE}).")
        ordered = sorted(normalized.values(), key=lambda item: (item.start_seconds, item.modality, item.evidence_id))
        serialized = [record.to_dict() for record in ordered]
        digest = hashlib.sha256(_canonical_json(serialized).encode("utf-8")).hexdigest()
        manifest = {
            "schema_version": SCHEMA_VERSION,
            "source_id": source_id,
            "record_count": len(serialized),
            "content_digest": digest,
            "source_metadata": dict(source_metadata or {}),
            "records": serialized,
        }
        encoded = json.dumps(manifest, ensure_ascii=False, indent=2, allow_nan=False)
        with _STORE_LOCK:
            fd, temporary = tempfile.mkstemp(prefix=f".{source_id}.", suffix=".tmp", dir=self.directory)
            try:
                with os.fdopen(fd, "w", encoding="utf-8") as stream:
                    stream.write(encoded)
                    stream.flush()
                    os.fsync(stream.fileno())
                os.replace(temporary, target)
            except Exception:
                try:
                    os.unlink(temporary)
                except OSError:
                    pass
                raise
        return {"source_id": source_id, "record_count": len(serialized), "content_digest": digest}

    def read(self, source_id: str) -> dict[str, Any] | None:
        path = self._path(source_id)
        try:
            manifest = json.loads(path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            return None
        except (OSError, json.JSONDecodeError):
            return None
        if not isinstance(manifest, dict):
            raise ValueError("Evidence manifest must be a JSON object.")
        if manifest.get("schema_version") != SCHEMA_VERSION:
            raise ValueError(f"Unsupported evidence schema version: {manifest.get('schema_version')!r}.")
        if manifest.get("source_id") != source_id:
            raise ValueError("Evidence manifest source_id mismatch.")
        raw_records = manifest.get("records")
        if not isinstance(raw_records, list) or len(raw_records) > MAX_RECORDS_PER_SOURCE:
            raise ValueError("Evidence manifest records are invalid or exceed the record limit.")
        records = [EvidenceRecord.from_dict(item) for item in raw_records]
        if any(record.source_id != source_id for record in records):
            raise ValueError("Evidence manifest contains a record for another source.")
        serialized = [record.to_dict() for record in records]
        digest = hashlib.sha256(_canonical_json(serialized).encode("utf-8")).hexdigest()
        if manifest.get("record_count") != len(records) or manifest.get("content_digest") != digest:
            raise ValueError("Evidence manifest integrity check failed.")
        return {
            **manifest,
            "records": records,
        }

    def query(
        self,
        source_id: str,
        modalities: Iterable[str] | None = None,
        start_seconds: float | None = None,
        end_seconds: float | None = None,
        text_query: str = "",
        limit: int = 1000,
    ) -> list[EvidenceRecord]:
        manifest = self.read(source_id)
        if not manifest:
            return []
        allowed = set(modalities) if modalities is not None else None
        if allowed is not None and not allowed.issubset(ALLOWED_MODALITIES):
            raise ValueError("Query contains an unsupported evidence modality.")
        start = None if start_seconds is None else max(0.0, float(start_seconds))
        end = None if end_seconds is None else max(0.0, float(end_seconds))
        if start is not None and end is not None and end < start:
            raise ValueError("end_seconds must be >= start_seconds.")
        terms = {term.lower() for term in re.findall(r"[\wÀ-ÖØ-öø-ÿ]+", text_query) if len(term) > 1}
        matches = []
        for record in manifest["records"]:
            if allowed is not None and record.modality not in allowed:
                continue
            if start is not None and record.end_seconds < start:
                continue
            if end is not None and record.start_seconds > end:
                continue
            if terms and not terms.intersection(re.findall(r"[\wÀ-ÖØ-öø-ÿ]+", record.text.lower())):
                continue
            matches.append(record)
        return matches[:max(0, min(int(limit), 10_000))]

    def delete(self, source_id: str) -> bool:
        path = self._path(source_id)
        with _STORE_LOCK:
            try:
                path.unlink()
                return True
            except FileNotFoundError:
                return False
