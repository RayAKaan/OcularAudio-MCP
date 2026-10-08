"""Reusable user-facing MCP prompts for common OcularAudio workflows.

Prompts are intentionally deterministic templates. They do not invoke an LLM or
perform analysis themselves; the connected MCP host supplies them to its model.
"""

PROMPT_NAMES = (
    "inspect_video",
    "search_video_evidence",
    "review_visual_evidence",
    "compare_videos",
)


def prompt_catalog() -> list[dict[str, object]]:
    return [
        {
            "name": "inspect_video",
            "description": "Build a grounded investigation request for one video.",
            "arguments": ["url", "focus"],
        },
        {
            "name": "search_video_evidence",
            "description": "Build a timestamp-focused evidence retrieval request.",
            "arguments": ["url", "query"],
        },
        {
            "name": "review_visual_evidence",
            "description": "Build a visual/OCR-focused review request.",
            "arguments": ["url", "focus"],
        },
        {
            "name": "compare_videos",
            "description": "Build a cross-video comparison request.",
            "arguments": ["sources", "question"],
        },
    ]


def _require(value: str, name: str) -> str:
    value = str(value or "").strip()
    if not value:
        raise ValueError(f"{name} is required")
    return value


def render_inspect_video(url: str, focus: str = "") -> str:
    focus = focus.strip() or "Identify the important claims, events, and supporting evidence."
    return (
        "Investigate this video using OcularAudio's verified evidence tools.\n\n"
        f"Source: {_require(url, 'url')}\n"
        f"Focus: {focus}\n\n"
        "Use timestamps for material claims. Distinguish transcript evidence, "
        "visual evidence, and OCR evidence. Do not invent details that are not "
        "supported by retrieved evidence."
    )


def render_search_video_evidence(url: str, query: str) -> str:
    return (
        "Find the strongest timestamped evidence for the following question.\n\n"
        f"Source: {_require(url, 'url')}\n"
        f"Question: {_require(query, 'query')}\n\n"
        "Search transcript and visual/OCR evidence when useful. Return the "
        "most relevant moments with timestamps and explain why each supports "
        "the answer."
    )


def render_visual_review(url: str, focus: str = "") -> str:
    focus = focus.strip() or "Identify meaningful visual changes, on-screen text, and objects."
    return (
        "Perform a visual evidence review of this video with OcularAudio.\n\n"
        f"Source: {_require(url, 'url')}\n"
        f"Focus: {focus}\n\n"
        "Prioritize visual frames and OCR, correlate them with nearby transcript "
        "evidence, and cite timestamps for observations."
    )


def render_compare_videos(sources: str, question: str) -> str:
    return (
        "Compare these media sources using OcularAudio's batch and cross-video "
        "evidence tools.\n\n"
        f"Sources: {_require(sources, 'sources')}\n"
        f"Question: {_require(question, 'question')}\n\n"
        "Normalize the comparison criteria, cite source-specific timestamps, "
        "separate evidence from inference, and identify meaningful similarities "
        "and differences."
    )
