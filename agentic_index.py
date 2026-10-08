"""Deterministic agentic planning and production-hardening primitives.

Phase 7 adds an inspectable execution planner, bounded retry/timeout policy,
audit records, health summaries, and safe resource limits. It deliberately
does not require a hosted LLM: the planner converts an intent into a stable
sequence over the existing evidence capabilities.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
import asyncio
import hashlib
import json
from pathlib import Path
import time
from typing import Any, Awaitable, Callable

from runtime_ops import MetricsRegistry, OperationTimer, rotate_audit_log


MAX_QUERY_LENGTH = 1000
MAX_STEPS = 8
MAX_RETRIES = 3
DEFAULT_TIMEOUT_SECONDS = 120.0


@dataclass(frozen=True)
class ExecutionPolicy:
    timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS
    max_retries: int = 2
    backoff_seconds: float = 0.25
    max_steps: int = MAX_STEPS

    def validate(self) -> "ExecutionPolicy":
        timeout = float(self.timeout_seconds)
        retries = int(self.max_retries)
        backoff = float(self.backoff_seconds)
        steps = int(self.max_steps)
        if not 0.001 <= timeout <= 900:
            raise ValueError("timeout_seconds must be between 0.001 and 900.")
        if not 0 <= retries <= MAX_RETRIES:
            raise ValueError(f"max_retries must be between 0 and {MAX_RETRIES}.")
        if not 0 <= backoff <= 30:
            raise ValueError("backoff_seconds must be between 0 and 30.")
        if not 1 <= steps <= MAX_STEPS:
            raise ValueError(f"max_steps must be between 1 and {MAX_STEPS}.")
        return ExecutionPolicy(timeout, retries, backoff, steps)


@dataclass(frozen=True)
class PlanStep:
    step_id: str
    operation: str
    reason: str
    required: bool = True

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class ExecutionPlan:
    plan_id: str
    intent: str
    query: str
    steps: list[PlanStep]
    policy: ExecutionPolicy

    def to_dict(self) -> dict[str, Any]:
        return {
            "plan_id": self.plan_id,
            "intent": self.intent,
            "query": self.query,
            "steps": [step.to_dict() for step in self.steps],
            "policy": asdict(self.policy),
        }


@dataclass(frozen=True)
class AuditRecord:
    timestamp: float
    operation: str
    status: str
    duration_ms: float
    detail: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def normalize_query(query: str) -> str:
    value = " ".join(str(query or "").split()).strip()
    if len(value) > MAX_QUERY_LENGTH:
        raise ValueError(f"query must be at most {MAX_QUERY_LENGTH} characters.")
    return value


def classify_intent(query: str, multi_video: bool = False) -> str:
    text = normalize_query(query).lower()
    if multi_video:
        if any(word in text for word in ("compare", "difference", "versus", "vs", "which")):
            return "compare_videos"
        return "search_videos"
    if any(word in text for word in ("ocr", "text on screen", "written")):
        return "inspect_ocr"
    if any(word in text for word in ("frame", "show", "screen", "visible", "chart", "diagram")):
        return "inspect_visual"
    if any(word in text for word in ("timeline", "when", "timestamp", "chapter")):
        return "timeline"
    if text:
        return "search_video"
    return "inspect_video"


def _plan_id(intent: str, query: str, steps: list[PlanStep]) -> str:
    payload = {"intent": intent, "query": query, "steps": [asdict(step) for step in steps]}
    return hashlib.sha256(json.dumps(payload, sort_keys=True).encode("utf-8")).hexdigest()[:24]


def build_execution_plan(
    query: str,
    *,
    multi_video: bool = False,
    policy: ExecutionPolicy | None = None,
) -> ExecutionPlan:
    query = normalize_query(query)
    policy = (policy or ExecutionPolicy()).validate()
    intent = classify_intent(query, multi_video)
    operations = {
        "inspect_video": [("inspect_source", "Establish source capabilities before expensive processing.")],
        "search_video": [("search_hybrid", "Use transcript and visual evidence for broad evidence retrieval.")],
        "inspect_visual": [
            ("search_hybrid", "Locate relevant evidence before visual inspection."),
            ("inspect_moment", "Inspect the strongest timestamp with targeted visual evidence."),
        ],
        "inspect_ocr": [
            ("search_visual", "Find visible text using the persistent visual index."),
            ("inspect_moment", "Verify nearby transcript and visual evidence."),
        ],
        "timeline": [("timeline", "Return timestamp-addressable evidence without loading the full transcript.")],
        "search_videos": [("search_batch", "Search multimodal evidence across all supplied sources.")],
        "compare_videos": [("compare_batch", "Run the same evidence contract across sources for comparison.")],
    }
    raw_steps = operations[intent]
    steps = [
        PlanStep(step_id=f"s{idx:02d}", operation=op, reason=reason)
        for idx, (op, reason) in enumerate(raw_steps, 1)
    ][: policy.max_steps]
    return ExecutionPlan(_plan_id(intent, query, steps), intent, query, steps, policy)


async def execute_with_policy(
    operation: str,
    worker: Callable[[], Awaitable[Any]],
    policy: ExecutionPolicy | None = None,
) -> tuple[Any, AuditRecord]:
    policy = (policy or ExecutionPolicy()).validate()
    started = time.monotonic()
    metrics = MetricsRegistry()
    timer = OperationTimer(metrics, operation)
    last_error: Exception | None = None
    for attempt in range(policy.max_retries + 1):
        try:
            result = await asyncio.wait_for(worker(), timeout=policy.timeout_seconds)
            timer.finish("success")
            return result, AuditRecord(
                time.time(), operation, "success",
                round((time.monotonic() - started) * 1000, 3),
                {"attempt": attempt + 1, "metrics": metrics.snapshot()},
            )
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            last_error = exc
            if attempt < policy.max_retries:
                await asyncio.sleep(policy.backoff_seconds * (2 ** attempt))
    timer.finish("error")
    return None, AuditRecord(
        time.time(), operation, "error",
        round((time.monotonic() - started) * 1000, 3),
        {"attempt": policy.max_retries + 1, "error": str(last_error), "metrics": metrics.snapshot()},
    )


def health_report(
    capabilities: dict[str, Any],
    *,
    cache_dir: Path,
    batch_cache_dir: Path,
) -> dict[str, Any]:
    checks = {
        "ffmpeg": bool(capabilities.get("ffmpeg")),
        "opencv": bool(capabilities.get("opencv")),
        "cache_writable": cache_dir.exists() and cache_dir.is_dir(),
        "batch_cache_writable": batch_cache_dir.exists() and batch_cache_dir.is_dir(),
    }
    warnings: list[str] = []
    if not checks["ffmpeg"]:
        warnings.append("FFmpeg is unavailable; media extraction may be limited.")
    if not capabilities.get("whisper", {}).get("available"):
        warnings.append("No local Whisper engine is available; caption fallback may be required.")
    if not capabilities.get("tesseract", {}).get("available"):
        warnings.append("Tesseract is unavailable; OCR features may be limited.")
    return {
        "status": "healthy" if all(checks.values()) else "degraded",
        "checks": checks,
        "warnings": warnings,
        "cache_dir": str(cache_dir),
        "batch_cache_dir": str(batch_cache_dir),
    }


def append_audit_record(path: Path, record: AuditRecord) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    rotate_audit_log(path)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record.to_dict(), ensure_ascii=False) + "\n")


def read_audit_records(path: Path, limit: int = 50) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    limit = max(1, min(int(limit), 200))
    lines = path.read_text(encoding="utf-8").splitlines()
    records: list[dict[str, Any]] = []
    for line in lines[-limit:]:
        try:
            records.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return records
