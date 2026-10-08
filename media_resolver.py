"""Universal media source resolution for OcularAudio.

Phase 1 establishes one canonical representation for URLs, local media files,
and live sources. Extraction/analysis layers consume this representation instead
of making platform-specific assumptions.
"""

from __future__ import annotations

import hashlib
import mimetypes
import os
import re
import subprocess
import urllib.parse
from pathlib import Path
from typing import Any, Dict, Optional

from universal_sources import (
    DIRECT_MEDIA_EXTENSIONS,
    is_media_url_scheme,
    platform_from_extractor,
    platform_from_host,
    source_family,
)

SUPPORTED_ANALYSIS_LEVELS = ("glance", "understand", "deep", "omniscient")
ANALYSIS_LEVEL_ALIASES = {
    "minimal": "glance",
    "basic": "glance",
    "standard": "understand",
    "normal": "understand",
    "maximum": "omniscient",
    "extreme": "omniscient",
}

VIDEO_EXTENSIONS = set(DIRECT_MEDIA_EXTENSIONS) - AUDIO_EXTENSIONS if "AUDIO_EXTENSIONS" in globals() else {".3gp", ".avi", ".flv", ".m4v", ".mkv", ".mov", ".mp4", ".mpeg", ".mpg", ".ts", ".webm", ".wmv", ".m3u8", ".mpd"}
AUDIO_EXTENSIONS = {".aac", ".flac", ".m4a", ".mp3", ".ogg", ".opus", ".wav", ".weba"}

PLATFORM_HOSTS = {
    "youtube": ("youtube.com", "youtu.be", "youtube-nocookie.com"),
    "tiktok": ("tiktok.com",),
    "instagram": ("instagram.com",),
    "facebook": ("facebook.com", "fb.watch"),
    "x": ("x.com", "twitter.com"),
    "twitch": ("twitch.tv",),
    "vimeo": ("vimeo.com",),
    "reddit": ("reddit.com", "redd.it"),
    "dailymotion": ("dailymotion.com", "dai.ly"),
    "bilibili": ("bilibili.com", "b23.tv"),
    "loom": ("loom.com",),
    "rumble": ("rumble.com",),
}

PLATFORM_ALIASES = {
    "youtube": "youtube",
    "youtube:tab": "youtube",
    "youtube:clip": "youtube",
    "youtube:playlist": "youtube",
    "tiktok": "tiktok",
    "instagram": "instagram",
    "facebook": "facebook",
    "twitter": "x",
    "twitter:tweet": "x",
    "twitch": "twitch",
    "vimeo": "vimeo",
    "reddit": "reddit",
    "dailymotion": "dailymotion",
    "bilibili": "bilibili",
    "loom": "loom",
    "rumble": "rumble",
}


def normalize_analysis_level(level: str) -> str:
    value = str(level or "understand").strip().lower()
    value = ANALYSIS_LEVEL_ALIASES.get(value, value)
    if value not in SUPPORTED_ANALYSIS_LEVELS:
        raise ValueError(
            f"Invalid analysis level '{level}'. "
            f"Choose one of: {', '.join(SUPPORTED_ANALYSIS_LEVELS)}."
        )
    return value


def analysis_policy(level: str) -> Dict[str, Any]:
    """Return deterministic ingestion policy for the four user-facing levels."""
    level = normalize_analysis_level(level)
    policies = {
        "glance": {
            "level": "glance",
            "frame_strategy": "sparse",
            "ocr": False,
            "visual_analysis": "minimal",
            "embeddings": False,
            "scene_detection": "basic",
            "preserve_raw": False,
        },
        "understand": {
            "level": "understand",
            "frame_strategy": "important",
            "ocr": True,
            "visual_analysis": "standard",
            "embeddings": True,
            "scene_detection": "standard",
            "preserve_raw": False,
        },
        "deep": {
            "level": "deep",
            "frame_strategy": "dense",
            "ocr": True,
            "visual_analysis": "deep",
            "embeddings": True,
            "scene_detection": "advanced",
            "preserve_raw": True,
        },
        "omniscient": {
            "level": "omniscient",
            "frame_strategy": "maximum",
            "ocr": True,
            "visual_analysis": "maximum",
            "embeddings": True,
            "scene_detection": "maximum",
            "preserve_raw": True,
        },
    }
    return dict(policies[level])


def _hostname(url: str) -> str:
    host = urllib.parse.urlparse(url).hostname or ""
    return host.lower().removeprefix("www.")


def detect_platform(url: str, extractor_key: str = "") -> str:
    """Resolve a stable platform family without hard-coding every extractor."""
    key = (extractor_key or "").lower()
    for prefix, platform in PLATFORM_ALIASES.items():
        if key == prefix or key.startswith(prefix + ":"):
            return platform

    host = _hostname(url)
    for platform, hosts in PLATFORM_HOSTS.items():
        if any(host == item or host.endswith("." + item) for item in hosts):
            return platform

    # Phase 8 keeps unknown hosts first-class. The universal source catalog
    # provides additional host hints, while yt-dlp extractor keys remain the
    # authoritative discovery mechanism after resolution.
    return platform_from_host(host)


def _is_url(source: str) -> bool:
    try:
        parsed = urllib.parse.urlparse(source)
        return is_media_url_scheme(parsed.scheme)
    except ValueError:
        return False


def _local_path(source: str) -> Optional[Path]:
    value = source.strip()
    if value.startswith("file://"):
        parsed = urllib.parse.urlparse(value)
        value = urllib.parse.unquote(parsed.path)
        if os.name == "nt" and re.match(r"^/[A-Za-z]:", value):
            value = value[1:]
    path = Path(os.path.expanduser(value))
    if path.exists() and path.is_file():
        return path.resolve()
    return None


def classify_source(source: str) -> Dict[str, Any]:
    """Classify a source without network access."""
    if not isinstance(source, str) or not source.strip():
        raise ValueError("Media source must be a non-empty URL or local file path.")

    value = source.strip()
    local = _local_path(value)
    if local:
        mime = mimetypes.guess_type(local.name)[0] or ""
        suffix = local.suffix.lower()
        if mime.startswith("audio/") or suffix in AUDIO_EXTENSIONS:
            media_type = "audio"
        elif mime.startswith("video/") or suffix in VIDEO_EXTENSIONS:
            media_type = "video"
        else:
            media_type = "unknown"
        return {
            "source": str(local),
            "source_kind": "local_file",
            "platform": "local",
            "media_type": media_type,
            "is_live": False,
            "extension": suffix,
            "exists": True,
        }

    if not _is_url(value):
        raise ValueError(
            "Unsupported media source. Provide an http(s)/rtmp URL or an existing local media file."
        )

    scheme = urllib.parse.urlparse(value).scheme.lower()
    suffix = Path(urllib.parse.urlparse(value).path).suffix.lower()
    media_type = "audio" if suffix in AUDIO_EXTENSIONS else "video" if suffix in VIDEO_EXTENSIONS else "unknown"

    return {
        "source": value,
        "source_kind": "url",
        "platform": detect_platform(value),
        "source_family": source_family(detect_platform(value)),
        "media_type": media_type,
        "is_live": scheme.startswith("rtmp"),
        "extension": suffix,
        "exists": True,
    }


def _ffprobe_local(path: Path) -> Dict[str, Any]:
    result = subprocess.run(
        [
            "ffprobe", "-v", "error", "-show_entries",
            "format=duration,size,format_name:stream=index,codec_type,codec_name,width,height",
            "-of", "json", str(path),
        ],
        capture_output=True,
        text=True,
        timeout=15,
        check=False,
    )
    if result.returncode != 0:
        return {}
    try:
        import json
        return json.loads(result.stdout or "{}")
    except Exception:
        return {}


def resolve_media_source(source: str, cookies_path: str = "") -> Dict[str, Any]:
    """Return the canonical OcularAudio media object.

    Network resolution is performed through yt-dlp for URLs. Raw signed stream
    URLs are never returned in this object; callers should consume the resolver
    result internally and avoid exposing credentials or transient URLs.
    """
    classified = classify_source(source)
    canonical: Dict[str, Any] = {
        **classified,
        "source_id": stable_source_id(source),
        "title": Path(source).stem if classified["source_kind"] == "local_file" else "",
        "uploader": "",
        "duration_seconds": None,
        "is_live": classified["is_live"],
        "extractor": None,
        "has_audio": classified["media_type"] in {"audio", "video"},
        "has_video": classified["media_type"] == "video",
        "has_captions": False,
        "capabilities": {
            "metadata": True,
            "audio": classified["media_type"] in {"audio", "video"},
            "video": classified["media_type"] == "video",
            "captions": False,
            "screenshots": classified["media_type"] == "video",
            "live": classified["is_live"],
        },
    }

    if classified["source_kind"] == "local_file":
        probe = _ffprobe_local(Path(classified["source"]))
        streams = probe.get("streams", []) if isinstance(probe, dict) else []
        has_audio = any(s.get("codec_type") == "audio" for s in streams)
        has_video = any(s.get("codec_type") == "video" for s in streams)
        duration = (probe.get("format") or {}).get("duration")
        canonical["duration_seconds"] = float(duration) if duration else None
        canonical["has_audio"] = has_audio
        canonical["has_video"] = has_video
        canonical["media_type"] = "video" if has_video else "audio" if has_audio else canonical["media_type"]
        canonical["capabilities"].update({"audio": has_audio, "video": has_video, "screenshots": has_video})
        return canonical

    try:
        import yt_dlp
        opts = {
            "quiet": True,
            "no_warnings": True,
            "noplaylist": True,
            "socket_timeout": 30,
        }
        if cookies_path:
            opts["cookiefile"] = cookies_path
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(source, download=False)

        extractor = str(info.get("extractor_key") or info.get("extractor") or "")
        formats = info.get("formats") or []
        has_audio = any(f.get("acodec") not in (None, "none") for f in formats)
        has_video = any(f.get("vcodec") not in (None, "none") for f in formats)
        subtitles = info.get("subtitles") or {}
        automatic = info.get("automatic_captions") or {}
        is_live = bool(info.get("is_live"))
        protocol = ""
        if formats:
            protocol = str((formats[-1] or {}).get("protocol") or "")

        canonical.update({
            "platform": detect_platform(source, extractor),
            "source_family": source_family(platform_from_extractor(extractor) if extractor else detect_platform(source)),
            "extractor": extractor or None,
            "extractor_platform": platform_from_extractor(extractor),
            "title": info.get("title") or canonical["title"],
            "uploader": info.get("uploader") or info.get("channel") or "",
            "duration_seconds": info.get("duration"),
            "is_live": is_live,
            "has_audio": has_audio,
            "has_video": has_video,
            "media_type": "video" if has_video else "audio" if has_audio else canonical["media_type"],
            "protocol": protocol,
            "capabilities": {
                "metadata": True,
                "audio": has_audio,
                "video": has_video,
                "captions": bool(subtitles or automatic),
                "screenshots": has_video,
                "live": is_live,
            },
        })
    except Exception as exc:
        canonical["resolution_error"] = str(exc)

    return canonical


def stable_source_id(source: str) -> str:
    """Create a collision-resistant source ID while preserving YouTube IDs."""
    youtube_id = re.search(
        r"(?:v=|/embed/|/v/|youtu\.be/)([0-9A-Za-z_-]{11})(?:\b|[&?/])",
        source,
    )
    if youtube_id:
        return youtube_id.group(1)
    local = _local_path(source)
    if local:
        stat = local.stat()
        material = f"{local}:{stat.st_size}:{stat.st_mtime_ns}".encode("utf-8")
    else:
        material = source.strip().encode("utf-8")
    return hashlib.sha256(material).hexdigest()[:32]
