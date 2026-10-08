"""MCP-native protocol contract and interoperability metadata for OcularAudio.

Phase 10 makes the server self-describing: tools have stable behavioral
annotations, the server exposes a machine-readable contract, and hosts can
discover the same capability model through MCP resources.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

CONTRACT_VERSION = "1.0"
MCP_PROTOCOL_REVISION = "2026-07-28"

TOOL_NAMES = (
    "get_ocular_audio_transcript",
    "get_ocular_audio_video_screenshots",
    "index_ocular_audio_video_visuals",
    "search_ocular_audio_visuals",
    "get_ocular_audio_video_frame",
    "get_ocular_audio_video_frame_burst",
    "crop_ocular_audio_video_frame",
    "search_ocular_audio_hybrid",
    "analyze_ocular_audio_multimodal",
    "inspect_ocular_audio_multimodal_moment",
    "plan_ocular_audio_analysis",
    "get_ocular_audio_health",
    "get_ocular_audio_audit",
    "run_ocular_audio_analysis",
    "analyze_ocular_audio_batch",
    "search_ocular_audio_videos",
    "compare_ocular_audio_videos",
    "get_ocular_audio_batch",
    "list_ocular_audio_batches",
    "inspect_ocular_audio_source",
    "get_ocular_audio_capabilities",
    "get_ocular_audio_metadata",
    "get_ocular_audio_chapters",
    "list_ocular_audio_cache",
    "clear_ocular_audio_cache",
    "get_ocular_audio_video_context",
    "search_ocular_audio_video",
    "get_ocular_audio_video_timeline",
    "inspect_ocular_audio_moment",
    "search_ocular_audio_cache",
    "get_ocular_audio_contract",
    "get_ocular_audio_identity",
)

READ_ONLY_PREFIXES = (
    "get_",
    "list_",
    "search_",
    "inspect_",
    "plan_",
)

DESTRUCTIVE_TOOLS = {"clear_ocular_audio_cache"}

WRITE_TOOLS = {
    "index_ocular_audio_video_visuals",
    "analyze_ocular_audio_batch",
    "run_ocular_audio_analysis",
    "get_ocular_audio_video_context",
    "get_ocular_audio_video_screenshots",
    "get_ocular_audio_video_frame",
    "get_ocular_audio_video_frame_burst",
    "crop_ocular_audio_video_frame",
    "analyze_ocular_audio_multimodal",
    "inspect_ocular_audio_moment",
    "inspect_ocular_audio_multimodal_moment",
}

OPEN_WORLD_TOOLS = {
    name for name in TOOL_NAMES
    if name not in {
        "get_ocular_audio_health",
        "get_ocular_audio_audit",
        "get_ocular_audio_capabilities",
        "get_ocular_audio_contract",
        "list_ocular_audio_cache",
        "clear_ocular_audio_cache",
        "get_ocular_audio_batch",
        "list_ocular_audio_batches",
        "search_ocular_audio_cache",
    }
}


@dataclass(frozen=True)
class ToolContract:
    name: str
    read_only: bool
    destructive: bool
    idempotent: bool
    open_world: bool
    category: str


def _category(name: str) -> str:
    if "batch" in name or "videos" in name:
        return "batch"
    if "visual" in name or "frame" in name or "moment" in name:
        return "visual"
    if "hybrid" in name or "multimodal" in name:
        return "multimodal"
    if "audit" in name or "health" in name or "contract" in name:
        return "operations"
    if "cache" in name:
        return "cache"
    if "source" in name or "metadata" in name or "chapters" in name:
        return "source"
    if "plan" in name or "analysis" in name:
        return "orchestration"
    return "evidence"


def tool_contract(name: str) -> ToolContract:
    if name not in TOOL_NAMES:
        raise ValueError(f"Unknown OcularAudio tool: {name}")
    destructive = name in DESTRUCTIVE_TOOLS
    read_only = (
        name not in WRITE_TOOLS
        and not destructive
        and any(name.startswith(prefix) for prefix in READ_ONLY_PREFIXES)
    )
    return ToolContract(
        name=name,
        read_only=read_only,
        destructive=destructive,
        idempotent=read_only or name in {"clear_ocular_audio_cache"},
        open_world=name in OPEN_WORLD_TOOLS,
        category=_category(name),
    )


def tool_contracts() -> list[dict[str, Any]]:
    return [asdict(tool_contract(name)) for name in TOOL_NAMES]


def resource_catalog() -> list[dict[str, str]]:
    return [
        {
            "uri": "ocularaudio://capabilities",
            "mime_type": "application/json",
            "description": "Current OcularAudio dependency and feature capabilities.",
        },
        {
            "uri": "ocularaudio://modes",
            "mime_type": "application/json",
            "description": "Lite, Intelligence, Deep, and Auto capability-mode policies.",
        },
        {
            "uri": "ocularaudio://health",
            "mime_type": "application/json",
            "description": "Current cache, dependency, and production health report.",
        },
        {
            "uri": "ocularaudio://contract",
            "mime_type": "application/json",
            "description": "Machine-readable MCP contract, tool annotations, and resource catalog.",
        },
    ]


def server_contract(version: str, capabilities: dict[str, Any], prompts: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    return {
        "contract_version": CONTRACT_VERSION,
        "mcp_protocol_revision": MCP_PROTOCOL_REVISION,
        "server": {
            "name": "OcularAudio Server",
            "version": version,
            "transport": "stdio",
            "local_first": True,
        },
        "tools": tool_contracts(),
        "resources": resource_catalog(),
        "prompts": prompts or [],
        "capability_modes": capabilities.get("capability_modes", {}),
        "source_coverage": capabilities.get("source_coverage", {}),
        "security": capabilities.get("security", {}),
        "backward_compatible": {
            "text_content": True,
            "structured_content": True,
            "legacy_mcp_clients": True,
        },
        "transports": ["stdio", "streamable-http"],
        "superseded_transports": ["sse"],
    }


def validate_contract() -> None:
    names = [item["name"] for item in tool_contracts()]
    if len(names) != len(set(names)):
        raise ValueError("Tool contract contains duplicate tool names.")
    resources = [item["uri"] for item in resource_catalog()]
    if len(resources) != len(set(resources)):
        raise ValueError("Resource catalog contains duplicate URIs.")
    if not all(item["name"] in TOOL_NAMES for item in tool_contracts()):
        raise ValueError("Tool contract contains an unknown tool.")


def tool_annotations(name: str) -> Any:
    """Return MCP ToolAnnotations without making the contract module import-time fragile."""
    from mcp.types import ToolAnnotations

    contract = tool_contract(name)
    return ToolAnnotations(
        read_only_hint=contract.read_only,
        destructive_hint=contract.destructive,
        idempotent_hint=contract.idempotent,
        open_world_hint=contract.open_world,
    )


validate_contract()
