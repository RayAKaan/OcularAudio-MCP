"""Phase 9 capability modes for OcularAudio.

One universal source layer serves three processing modes. Modes change analysis
depth, evidence breadth, and response richness; they do not change source
coverage or require separate packages.
"""
from __future__ import annotations
from dataclasses import dataclass
from typing import Any, Dict, Tuple

MODES = ("lite", "intelligence", "deep", "auto")
MODE_ALIASES = {"light":"lite","basic":"lite","smart":"intelligence","standard":"intelligence","maximum":"deep","extreme":"deep"}

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

MODE_POLICIES: Dict[str, CapabilityMode] = {
    "lite": CapabilityMode("lite","Fast everyday media understanding","glance",8,"sparse",False,False,False,False),
    "intelligence": CapabilityMode("intelligence","Rich evidence retrieval and multimodal analysis","understand",24,"important",True,True,True,True),
    "deep": CapabilityMode("deep","Maximum practical evidence and orchestration","omniscient",64,"maximum",True,True,True,True),
}

def normalize_mode(mode: str) -> str:
    value = str(mode or "auto").strip().lower()
    value = MODE_ALIASES.get(value, value)
    if value not in MODES:
        raise ValueError(f"Invalid capability mode '{mode}'. Choose one of: lite, intelligence, deep, auto.")
    return value

def resolve_mode(mode: str, query: str = "") -> str:
    value = normalize_mode(mode)
    if value != "auto":
        return value
    text = str(query or "").lower()
    deep_markers = ("exhaustive","every","all occurrences","comprehensive","deep analysis","everything you can find","in detail")
    intelligence_markers = ("compare","find","search","show","analyze","explain","ocr","visual","timeline","across videos")
    if any(marker in text for marker in deep_markers):
        return "deep"
    if any(marker in text for marker in intelligence_markers):
        return "intelligence"
    return "lite"

def get_mode_policy(mode: str, query: str = "") -> CapabilityMode:
    resolved = resolve_mode(mode, query)
    return MODE_POLICIES[resolved]

def mode_capabilities() -> Dict[str, Any]:
    return {
        "default": "auto",
        "available_modes": list(MODES),
        "policies": {
            name: {
                "description": policy.description,
                "analysis_depth": policy.analysis_depth,
                "max_evidence": policy.max_evidence,
                "visual_strategy": policy.visual_strategy,
                "ocr": policy.ocr,
                "multimodal": policy.multimodal,
                "batch": policy.batch,
                "agentic": policy.agentic,
            }
            for name, policy in MODE_POLICIES.items()
        },
        "shared_source_coverage": True,
        "single_package": True,
        "single_local_mcp": True,
    }

def mode_output_contract(mode: str, query: str = "") -> Dict[str, Any]:
    policy = get_mode_policy(mode, query)
    return {
        "requested_mode": normalize_mode(mode),
        "resolved_mode": policy.name,
        "analysis_depth": policy.analysis_depth,
        "max_evidence": policy.max_evidence,
        "response_profile": policy.name,
        "source_coverage_shared": True,
    }

def is_feature_allowed(mode: str, feature: str, query: str = "") -> bool:
    policy = get_mode_policy(mode, query)
    return bool(getattr(policy, feature, False)) if hasattr(policy, feature) else feature in {"metadata","transcript","timeline"}
