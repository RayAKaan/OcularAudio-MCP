"""Phase 13 runtime observability and operational reliability primitives.

The module is dependency-light and process-local by design. It provides
bounded counters/timers, readiness checks, and safe audit retention without
introducing a telemetry service or database requirement.
"""

from __future__ import annotations

from collections import defaultdict, deque
from dataclasses import dataclass
import json
from pathlib import Path
import threading
import time
from typing import Any, Callable


MAX_METRIC_KEYS = 256
DEFAULT_AUDIT_MAX_BYTES = 5 * 1024 * 1024
DEFAULT_AUDIT_MAX_FILES = 5


@dataclass(frozen=True)
class ReadinessCheck:
    name: str
    ready: bool
    detail: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {"name": self.name, "ready": self.ready, "detail": self.detail}


class MetricsRegistry:
    """Bounded in-process metrics suitable for local and single-process servers."""

    def __init__(self, max_keys: int = MAX_METRIC_KEYS) -> None:
        self._max_keys = max(1, int(max_keys))
        self._lock = threading.Lock()
        self._counters: dict[str, int] = defaultdict(int)
        self._durations: dict[str, deque[float]] = defaultdict(lambda: deque(maxlen=256))

    def increment(self, name: str, amount: int = 1) -> None:
        key = str(name).strip()[:128] or "unknown"
        with self._lock:
            if key not in self._counters and len(self._counters) >= self._max_keys:
                key = "other"
            self._counters[key] += int(amount)

    def observe(self, name: str, milliseconds: float) -> None:
        key = str(name).strip()[:128] or "unknown"
        with self._lock:
            if key not in self._durations and len(self._durations) >= self._max_keys:
                key = "other"
            self._durations[key].append(max(0.0, float(milliseconds)))

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            counters = dict(self._counters)
            durations = {
                key: {
                    "count": len(values),
                    "avg_ms": round(sum(values) / len(values), 3) if values else 0.0,
                    "max_ms": round(max(values), 3) if values else 0.0,
                }
                for key, values in self._durations.items()
            }
        return {"counters": counters, "durations": durations}


GLOBAL_METRICS = MetricsRegistry()


class OperationTimer:
    def __init__(self, metrics: MetricsRegistry, operation: str) -> None:
        self.metrics = metrics
        self.operation = operation
        self.started = time.monotonic()

    def finish(self, status: str = "success") -> float:
        elapsed = (time.monotonic() - self.started) * 1000
        self.metrics.increment(f"operations.{self.operation}.{status}")
        self.metrics.observe(f"operations.{self.operation}", elapsed)
        return elapsed


def build_readiness(
    *,
    checks: list[ReadinessCheck],
    version: str,
    metrics: MetricsRegistry,
) -> dict[str, Any]:
    ready = all(check.ready for check in checks)
    return {
        "status": "ready" if ready else "not_ready",
        "version": version,
        "checks": [check.to_dict() for check in checks],
        "metrics": metrics.snapshot(),
    }


def rotate_audit_log(
    path: Path,
    *,
    max_bytes: int = DEFAULT_AUDIT_MAX_BYTES,
    max_files: int = DEFAULT_AUDIT_MAX_FILES,
) -> list[str]:
    """Rotate an audit JSONL file without deleting the active log."""
    max_bytes = max(1024, int(max_bytes))
    max_files = max(1, min(int(max_files), 20))
    if not path.exists() or path.stat().st_size <= max_bytes:
        return []

    rotated: list[str] = []
    for index in range(max_files - 1, 0, -1):
        src = path.with_name(f"{path.name}.{index}")
        dst = path.with_name(f"{path.name}.{index + 1}")
        if src.exists():
            if index + 1 > max_files:
                src.unlink()
            else:
                src.replace(dst)
                rotated.append(str(dst))
    first = path.with_name(f"{path.name}.1")
    if first.exists():
        first.unlink()
    path.replace(first)
    path.touch()
    rotated.append(str(first))
    return rotated


def validate_retention(max_bytes: int, max_files: int) -> tuple[int, int]:
    bytes_limit = int(max_bytes)
    files_limit = int(max_files)
    if bytes_limit < 1024:
        raise ValueError("max_bytes must be at least 1024.")
    if not 1 <= files_limit <= 20:
        raise ValueError("max_files must be between 1 and 20.")
    return bytes_limit, files_limit
