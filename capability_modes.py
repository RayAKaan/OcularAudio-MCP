"""Four-level capability intelligence and deterministic execution budgets.

Modes are execution policies, not labels. The same source resolver is shared by
all modes; the engine chooses bounded analysis depth, evidence, visual sampling,
optional features, retries, concurrency, and fallbacks from request intent and
runtime capabilities.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
import math
from typing import Any, Mapping

MODES = ("lite", "intelligence", "deep", "auto")
MODE_ALIASES = {
    "light": "lite", "basic": "lite", "smart": "intelligence",
    "standard": "intelligence", "maximum": "deep", "extreme": "deep",
}
MAX_SOURCES = 32
MAX_BUDGET_SECONDS = 900.0


@dataclass(frozen=True)
class CapabilityMode:
    name: str
    description: str
    analysis_depth: str
    max_evidence: int
    visual_strategy: str
    ocr: bool
    multimodal: bool
    batch: bool
    agentic: bool
    max_frames: int
    max_sources: int
    max_runtime_seconds: float
    max_retries: int
    max_concurrency: int
    default_interval_seconds: float
    min_interval_seconds: float
    max_steps: int

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


MODE_POLICIES: dict[str, CapabilityMode] = {
    "lite": CapabilityMode(
        "lite", "Fast, low-cost transcript and metadata inspection",
        "glance", 8, "sparse", False, False, False, False,
        8, 1, 45.0, 0, 1, 30.0, 15.0, 2,
    ),
    "intelligence": CapabilityMode(
        "intelligence", "Balanced evidence retrieval with optional OCR and multimodal alignment",
        "understand", 24, "important", True, True, True, True,
        24, 10, 180.0, 1, 2, 10.0, 5.0, 5,
    ),
    "deep": CapabilityMode(
        "deep", "Expanded evidence coverage and bounded multi-step investigation",
        "omniscient", 64, "maximum", True, True, True, True,
        64, 32, 600.0, 2, 4, 3.0, 1.0, 8,
    ),
}


def normalize_mode(mode: str | None) -> str:
    value = str(mode or "auto").strip().lower()
    value = MODE_ALIASES.get(value, value)
    if value not in MODES:
        raise ValueError(f"Invalid capability mode '{mode}'. Choose one of: {', '.join(MODES)}.")
    return value


def _query_features(query: str) -> set[str]:
    text = " ".join(str(query or "").lower().split())
    features: set[str] = set()
    if any(marker in text for marker in (
        "exhaustive", "every occurrence", "all occurrences", "comprehensive",
        "deep analysis", "everything you can find", "in detail", "all details",
        "investigate thoroughly",
    )):
        features.add("deep")
    if any(marker in text for marker in ("ocr", "text on screen", "written on screen", "read the text")):
        features.add("ocr")
    if any(marker in text for marker in (
        "visual", "frame", "show", "screen", "chart", "diagram", "image",
        "what appears", "what is shown",
    )):
        features.add("visual")
    if any(marker in text for marker in (
        "multimodal", "align speech", "align transcript", "audio and video",
        "visual and transcript",
    )):
        features.add("multimodal")
    if any(marker in text for marker in (
        "compare", "versus", " vs ", "across videos", "multiple videos", "batch", "cross-video",
    )):
        features.add("batch")
    if any(marker in text for marker in (
        "find", "search", "compare", "show", "analyze", "analyse", "explain",
        "timeline", "when", "timestamp", "chapter",
    )):
        features.add("retrieval")
    return features


def _auto_mode(
    query: str,
    *,
    source_count: int = 1,
    estimated_duration_seconds: float | None = None,
    budget_seconds: float | None = None,
    requested_features: tuple[str, ...] | list[str] | set[str] | None = None,
    multi_video: bool = False,
) -> tuple[str, str]:
    features = _query_features(query)
    features.update(str(item).strip().lower() for item in (requested_features or []))
    if "deep" in features:
        return "deep", "The request explicitly asks for exhaustive or comprehensive coverage."
    if source_count > MODE_POLICIES["intelligence"].max_sources:
        return "deep", "The source count exceeds the balanced-mode limit."
    if source_count > 1 or multi_video or "batch" in features:
        return "intelligence", "Multi-source work requires batch-capable analysis."
    if "agentic" in features:
        return "intelligence", "Agentic execution requires a mode with bounded orchestration enabled."
    if budget_seconds is not None and budget_seconds <= MODE_POLICIES["lite"].max_runtime_seconds:
        if features & {"ocr", "visual", "multimodal", "batch"}:
            return "intelligence", "The requested evidence features require more than Lite mode."
        return "lite", "The requested time budget favors the fastest mode."
    if estimated_duration_seconds is not None and estimated_duration_seconds >= 3600:
        return "intelligence", "Long media benefits from balanced evidence sampling."
    if features & {"ocr", "visual", "multimodal", "retrieval"}:
        return "intelligence", "The requested task benefits from evidence retrieval or visual analysis."
    return "lite", "A concise overview is sufficient for the request."


def resolve_mode(
    mode: str,
    query: str = "",
    *,
    source_count: int = 1,
    estimated_duration_seconds: float | None = None,
    budget_seconds: float | None = None,
    requested_features: tuple[str, ...] | list[str] | set[str] | None = None,
    multi_video: bool = False,
) -> str:
    value = normalize_mode(mode)
    if value != "auto":
        return value
    return _auto_mode(
        query, source_count=source_count,
        estimated_duration_seconds=estimated_duration_seconds,
        budget_seconds=budget_seconds,
        requested_features=requested_features, multi_video=multi_video,
    )[0]


@dataclass(frozen=True)
class ModeDecision:
    requested_mode: str
    resolved_mode: str
    reason: str
    source_count: int
    estimated_duration_seconds: float | None
    budget_seconds: float | None
    limits: dict[str, Any]
    features: dict[str, bool]
    adjustments: tuple[str, ...]
    capability_gaps: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["adjustments"] = list(self.adjustments)
        payload["capability_gaps"] = list(self.capability_gaps)
        return payload


def build_mode_decision(
    mode: str = "auto",
    query: str = "",
    *,
    source_count: int = 1,
    estimated_duration_seconds: float | None = None,
    available_capabilities: Mapping[str, Any] | None = None,
    budget_seconds: float | None = None,
    requested_features: tuple[str, ...] | list[str] | set[str] | None = None,
    multi_video: bool = False,
) -> ModeDecision:
    requested = normalize_mode(mode)
    try:
        source_count = int(source_count)
    except (TypeError, ValueError) as exc:
        raise ValueError("source_count must be an integer between 1 and 32.") from exc
    if not 1 <= source_count <= MAX_SOURCES:
        raise ValueError(f"source_count must be between 1 and {MAX_SOURCES}.")

    duration: float | None = None
    if estimated_duration_seconds is not None:
        duration = float(estimated_duration_seconds)
        if not math.isfinite(duration) or duration < 0:
            raise ValueError("estimated_duration_seconds must be a finite non-negative number.")
    budget: float | None = None
    if budget_seconds is not None:
        budget = float(budget_seconds)
        if not math.isfinite(budget) or not 0.001 <= budget <= MAX_BUDGET_SECONDS:
            raise ValueError(f"budget_seconds must be between 0.001 and {MAX_BUDGET_SECONDS:g}.")

    if requested == "auto":
        resolved, reason = _auto_mode(
            query, source_count=source_count, estimated_duration_seconds=duration,
            budget_seconds=budget, requested_features=requested_features, multi_video=multi_video,
        )
    else:
        resolved, reason = requested, f"The caller explicitly selected {requested} mode."

    policy = MODE_POLICIES[resolved]
    if source_count > policy.max_sources:
        raise ValueError(
            f"Mode '{resolved}' supports at most {policy.max_sources} sources; "
            f"received {source_count}. Use auto or deep mode, or split the request."
        )
    if (multi_video or source_count > 1) and not policy.batch:
        raise ValueError(f"Mode '{resolved}' does not support multi-source analysis. Use intelligence, deep, or auto.")

    capabilities = dict(available_capabilities or {})
    gaps: list[str] = []
    adjustments: list[str] = []
    features = {
        "metadata": True, "transcript": True, "timeline": True,
        "visual": policy.visual_strategy != "none", "ocr": policy.ocr,
        "multimodal": policy.multimodal, "batch": policy.batch, "agentic": policy.agentic,
    }
    if "opencv" in capabilities and not bool(capabilities.get("opencv")):
        features["visual"] = False
        features["multimodal"] = False
        gaps.append("OpenCV is unavailable; visual and multimodal processing are disabled.")
    if "ffmpeg" in capabilities and not bool(capabilities.get("ffmpeg")):
        features["visual"] = False
        features["multimodal"] = False
        gaps.append("FFmpeg is unavailable; media-frame processing may not run.")
    if "tesseract" in capabilities:
        tesseract_capability = capabilities.get("tesseract")
        tesseract_available = (
            bool(tesseract_capability.get("available"))
            if isinstance(tesseract_capability, Mapping)
            else bool(tesseract_capability)
        )
        if not tesseract_available:
            features["ocr"] = False
            gaps.append("Tesseract is unavailable; OCR is disabled for this execution.")
    if budget is not None and budget < policy.max_runtime_seconds:
        adjustments.append(f"Runtime ceiling reduced from {policy.max_runtime_seconds:g}s to the requested {budget:g}s budget.")
    for feature in sorted(set(str(item).strip().lower() for item in (requested_features or []))):
        if feature in features and not features[feature]:
            adjustments.append(f"Requested feature '{feature}' is unavailable in {resolved} mode or this runtime.")

    effective_runtime = min(policy.max_runtime_seconds, budget) if budget is not None else policy.max_runtime_seconds
    limits = {
        "max_evidence": policy.max_evidence, "max_frames": policy.max_frames,
        "max_sources": policy.max_sources, "max_runtime_seconds": effective_runtime,
        "max_retries": policy.max_retries, "max_concurrency": policy.max_concurrency,
        "default_interval_seconds": policy.default_interval_seconds,
        "min_interval_seconds": policy.min_interval_seconds, "max_steps": policy.max_steps,
    }
    return ModeDecision(
        requested, resolved, reason, source_count, duration, budget, limits, features,
        tuple(adjustments), tuple(gaps),
    )


def get_mode_policy(mode: str, query: str = "", **kwargs: Any) -> CapabilityMode:
    return MODE_POLICIES[resolve_mode(mode, query, **kwargs)]


def mode_capabilities() -> Dict[str, Any]:
    return {
        "default": "auto",
        "available_modes": list(MODES),
        "aliases": dict(MODE_ALIASES),
        "policies": {name: policy.to_dict() for name, policy in MODE_POLICIES.items()},
        "auto_selection": {
            "exhaustive_requests": "deep",
            "multi_source_requests": "intelligence or deep based on source count",
            "visual_ocr_and_retrieval_requests": "intelligence",
            "short_overviews": "lite",
            "runtime_capabilities": "disable unavailable optional features with an explicit gap report",
        },
        "decision_contract": [
            "requested_mode", "resolved_mode", "reason", "source_count",
            "estimated_duration_seconds", "budget_seconds", "limits",
            "features", "adjustments", "capability_gaps",
        ],
        "shared_source_coverage": True,
        "single_package": True,
        "single_local_mcp": True,
    }


def mode_output_contract(mode: str, query: str = "", **kwargs: Any) -> Dict[str, Any]:
    decision = build_mode_decision(mode, query, **kwargs)
    return {
        "requested_mode": decision.requested_mode,
        "resolved_mode": decision.resolved_mode,
        "analysis_depth": MODE_POLICIES[decision.resolved_mode].analysis_depth,
        "max_evidence": decision.limits["max_evidence"],
        "response_profile": decision.resolved_mode,
        "source_coverage_shared": True,
        "mode_decision": decision.to_dict(),
    }


def mode_execution_controls(
    mode: str = "auto",
    query: str = "",
    *,
    interval_seconds: float | None = None,
    top_k: int | None = None,
    enable_ocr: bool | None = None,
    max_concurrency: int | None = None,
    source_count: int = 1,
    estimated_duration_seconds: float | None = None,
    available_capabilities: Mapping[str, Any] | None = None,
    budget_seconds: float | None = None,
    requested_features: tuple[str, ...] | list[str] | set[str] | None = None,
    multi_video: bool = False,
) -> dict[str, Any]:
    decision = build_mode_decision(
        mode, query, source_count=source_count,
        estimated_duration_seconds=estimated_duration_seconds,
        available_capabilities=available_capabilities, budget_seconds=budget_seconds,
        requested_features=requested_features, multi_video=multi_video,
    )
    policy = MODE_POLICIES[decision.resolved_mode]
    if interval_seconds is None:
        interval = policy.default_interval_seconds
    else:
        interval = float(interval_seconds)
        if not math.isfinite(interval) or interval <= 0:
            raise ValueError("interval_seconds must be a finite positive number.")
        interval = max(interval, policy.min_interval_seconds)
    requested_top_k = policy.max_evidence if top_k is None else int(top_k)
    if requested_top_k < 1:
        raise ValueError("top_k must be at least 1.")
    effective_top_k = min(requested_top_k, policy.max_evidence)
    ocr_requested = policy.ocr if enable_ocr is None else bool(enable_ocr)
    effective_ocr = ocr_requested and decision.features["ocr"]
    requested_concurrency = policy.max_concurrency if max_concurrency is None else int(max_concurrency)
    if requested_concurrency < 1:
        raise ValueError("max_concurrency must be at least 1.")
    effective_concurrency = min(requested_concurrency, policy.max_concurrency)
    return {
        "decision": decision.to_dict(), "policy": policy.to_dict(),
        "interval_seconds": interval, "top_k": effective_top_k,
        "enable_ocr": effective_ocr, "max_concurrency": effective_concurrency,
    }


def is_feature_allowed(mode: str, feature: str, query: str = "", **kwargs: Any) -> bool:
    decision = build_mode_decision(mode, query, **kwargs)
    return bool(decision.features.get(str(feature).strip().lower(), False))
