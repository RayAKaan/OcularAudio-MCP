"""Batch and multi-video intelligence primitives for OcularAudio.

Phase 6 provides deterministic, bounded-concurrency orchestration over the
existing multimodal evidence layer. It keeps per-source failures isolated,
deduplicates sources, persists resumable batch results, and supports
cross-video ranking/comparison without introducing an external database.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
import hashlib
import json
from pathlib import Path
import re
from typing import Any, Awaitable, Callable, Iterable

TOKEN_RE = re.compile(r"[\\wÀ-ÖØ-öø-ÿ]+", re.UNICODE)
MAX_SOURCES = 32
MAX_CONCURRENCY = 4


@dataclass(frozen=True)
class BatchSource:
    source_id: str
    url: str
    label: str = ""
    metadata: dict[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class BatchItem:
    source: BatchSource
    status: str
    result: dict[str, Any] | None = None
    error: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "source": self.source.to_dict(),
            "status": self.status,
            "result": self.result,
            "error": self.error,
        }


def _tokens(text: str) -> set[str]:
    return {token.lower() for token in TOKEN_RE.findall(text or "")}


def parse_batch_manifest(manifest: str | Iterable[Any]) -> list[BatchSource]:
    """Parse a JSON manifest or iterable into a bounded, deduplicated source list."""
    if isinstance(manifest, str):
        raw = manifest.strip()
        if not raw:
            return []
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError:
            payload = [line.strip() for line in raw.splitlines() if line.strip()]
    else:
        payload = manifest

    if isinstance(payload, dict):
        payload = payload.get("videos", payload.get("sources", []))
    if not isinstance(payload, list):
        raise ValueError("Batch manifest must be a JSON array or an object with 'videos'/'sources'.")

    sources: list[BatchSource] = []
    seen: set[str] = set()
    for item in payload:
        if isinstance(item, str):
            url = item.strip()
            label = ""
            metadata = None
        elif isinstance(item, dict):
            url = str(item.get("url", item.get("source", ""))).strip()
            label = str(item.get("label", item.get("title", ""))).strip()
            metadata = item.get("metadata") if isinstance(item.get("metadata"), dict) else None
        else:
            continue
        if not url:
            continue
        source_id = stable_batch_source_id(url)
        if source_id in seen:
            continue
        seen.add(source_id)
        sources.append(BatchSource(source_id, url, label, metadata))

    if len(sources) > MAX_SOURCES:
        raise ValueError(f"Batch supports at most {MAX_SOURCES} unique sources.")
    return sources


def stable_batch_source_id(url: str) -> str:
    return hashlib.sha256(url.strip().encode("utf-8")).hexdigest()[:24]


def stable_batch_id(
    sources: Iterable[BatchSource],
    query: str = "",
    options: dict[str, Any] | None = None,
) -> str:
    payload = {
        "sources": sorted(source.source_id for source in sources),
        "query": query.strip(),
        "options": options or {},
    }
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()[:24]


def validate_concurrency(value: int) -> int:
    value = int(value)
    if value < 1 or value > MAX_CONCURRENCY:
        raise ValueError(f"max_concurrency must be between 1 and {MAX_CONCURRENCY}.")
    return value


async def run_batch(
    sources: Iterable[BatchSource],
    worker: Callable[[BatchSource], Awaitable[dict[str, Any]]],
    max_concurrency: int = 2,
) -> list[BatchItem]:
    """Run source workers with bounded concurrency and isolated failures."""
    limit = validate_concurrency(max_concurrency)
    unique: list[BatchSource] = []
    seen: set[str] = set()
    for source in sources:
        if source.source_id not in seen:
            seen.add(source.source_id)
            unique.append(source)

    semaphore = __import__("asyncio").Semaphore(limit)

    async def execute(source: BatchSource) -> BatchItem:
        async with semaphore:
            try:
                result = await worker(source)
                return BatchItem(source=source, status="success", result=result)
            except Exception as exc:
                return BatchItem(source=source, status="error", error=str(exc))

    return await __import__("asyncio").gather(*(execute(source) for source in unique))


def rank_cross_video_results(
    batch_items: Iterable[BatchItem],
    query: str = "",
    top_k: int = 12,
) -> list[dict[str, Any]]:
    """Rank multimodal moments across videos using transparent lexical/signal scoring."""
    query_tokens = _tokens(query)
    ranked: list[tuple[float, dict[str, Any]]] = []
    for item in batch_items:
        if item.status != "success" or not item.result:
            continue
        for moment in item.result.get("results", []):
            text = " ".join(
                [str(x.get("text", "")) for x in moment.get("transcript", [])]
                + [str(moment.get("ocr_text", ""))]
            )
            overlap = len(query_tokens & _tokens(text))
            query_score = overlap / len(query_tokens) if query_tokens else 0.0
            base = float(moment.get("evidence_score", 0.0))
            change = float(moment.get("visual_change_score", 0.0))
            score = round(query_score * 0.55 + base * 0.2 + change * 0.25, 6)
            enriched = {
                **moment,
                "source_id": item.source.source_id,
                "source_url": item.source.url,
                "source_label": item.source.label,
                "batch_score": score,
            }
            ranked.append((score, enriched))
    ranked.sort(key=lambda pair: (-pair[0], pair[1].get("source_id", ""), float(pair[1].get("timestamp_seconds", 0))))
    return [item for _, item in ranked[: max(1, min(int(top_k), 100))]]


def compare_batch_results(
    batch_items: Iterable[BatchItem],
    query: str = "",
) -> list[dict[str, Any]]:
    """Produce a comparable per-video scorecard for the same query."""
    query_tokens = _tokens(query)
    rows: list[dict[str, Any]] = []
    for item in batch_items:
        result = item.result or {}
        moments = result.get("results", [])
        best_score = 0.0
        matches = 0
        for moment in moments:
            text = " ".join(
                [str(x.get("text", "")) for x in moment.get("transcript", [])]
                + [str(moment.get("ocr_text", ""))]
            )
            overlap = len(query_tokens & _tokens(text))
            query_score = overlap / len(query_tokens) if query_tokens else 0.0
            score = query_score * 0.55 + float(moment.get("evidence_score", 0.0)) * 0.2 + float(moment.get("visual_change_score", 0.0)) * 0.25
            best_score = max(best_score, score)
            if query_score > 0:
                matches += 1
        rows.append({
            "source_id": item.source.source_id,
            "url": item.source.url,
            "label": item.source.label,
            "status": item.status,
            "error": item.error,
            "moment_count": len(moments),
            "query_match_count": matches,
            "best_score": round(best_score, 6),
        })
    rows.sort(key=lambda row: (-row["best_score"], row["source_id"]))
    return rows


def summarize_batch(batch_items: Iterable[BatchItem]) -> dict[str, Any]:
    items = list(batch_items)
    success = sum(item.status == "success" for item in items)
    errors = sum(item.status == "error" for item in items)
    moments = sum(len((item.result or {}).get("results", [])) for item in items if item.status == "success")
    modalities: set[str] = set()
    for item in items:
        for moment in (item.result or {}).get("results", []):
            modalities.update(moment.get("modalities", []))
    return {
        "source_count": len(items),
        "success_count": success,
        "error_count": errors,
        "moment_count": moments,
        "modalities": sorted(modalities),
        "complete": bool(items) and errors == 0,
    }


def write_batch_result(directory: Path, batch_id: str, payload: dict[str, Any]) -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    target = directory / f"{batch_id}.json"
    temporary = target.with_suffix(".tmp")
    temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    temporary.replace(target)
    return target


def read_batch_result(directory: Path, batch_id: str) -> dict[str, Any] | None:
    target = directory / f"{batch_id}.json"
    try:
        return json.loads(target.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
