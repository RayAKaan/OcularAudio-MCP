"""Universal source taxonomy and capability policy for OcularAudio.

Phase 8 separates source coverage from analysis depth. Every analysis mode uses
this same source resolver; platform families only describe discovery metadata.
Unknown web hosts remain first-class generic sources and may be resolved by
yt-dlp when an extractor is available.
"""

from __future__ import annotations

from typing import Any, Dict, Iterable, Tuple

SOURCE_FAMILIES: Dict[str, Tuple[str, ...]] = {
    "video_social": (
        "youtube", "tiktok", "instagram", "facebook", "x", "twitter",
        "snapchat", "linkedin", "pinterest", "tumblr", "vk", "ok",
    ),
    "video_platform": (
        "vimeo", "twitch", "kick", "rumble", "dailymotion", "bilibili",
        "loom", "streamable", "rutube", "odysee", "peertube",
    ),
    "audio_platform": (
        "soundcloud", "bandcamp", "mixcloud", "spotify", "audiomack",
    ),
    "media_archive": (
        "archive", "internet_archive", "ted", "patreon",
    ),
    "generic": ("generic_web",),
    "local": ("local",),
}

PLATFORM_HOSTS: Dict[str, Tuple[str, ...]] = {
    "snapchat": ("snapchat.com",),
    "linkedin": ("linkedin.com",),
    "pinterest": ("pinterest.com",),
    "tumblr": ("tumblr.com",),
    "vk": ("vk.com", "vkvideo.ru"),
    "ok": ("ok.ru",),
    "kick": ("kick.com",),
    "streamable": ("streamable.com",),
    "rutube": ("rutube.ru",),
    "odysee": ("odysee.com",),
    "peertube": ("peertube.social",),
    "soundcloud": ("soundcloud.com",),
    "bandcamp": ("bandcamp.com",),
    "mixcloud": ("mixcloud.com",),
    "spotify": ("spotify.com",),
    "audiomack": ("audiomack.com",),
    "archive": ("archive.org",),
    "internet_archive": ("web.archive.org",),
    "ted": ("ted.com",),
    "patreon": ("patreon.com",),
}

EXTRACTOR_ALIASES: Dict[str, str] = {
    "twitter": "x",
    "twitter:tweet": "x",
    "youtube:tab": "youtube",
    "youtube:clip": "youtube",
    "youtube:playlist": "youtube",
    "internetarchive": "internet_archive",
    "archiveorg": "archive",
    "peertube": "peertube",
    "odysse": "odysee",
}

MEDIA_URL_SCHEMES = {
    "http", "https", "rtmp", "rtmps", "rtmpe", "rtmpt", "rtmpts",
    "rtsp", "srt", "udp",
}

DIRECT_MEDIA_EXTENSIONS = {
    ".3gp", ".aac", ".avi", ".flac", ".flv", ".m4a", ".m4v", ".mkv",
    ".mov", ".mp3", ".mp4", ".mpeg", ".mpg", ".ogg", ".opus", ".ts",
    ".wav", ".webm", ".weba", ".wmv", ".m3u8", ".mpd",
}


def _matches_host(host: str, candidate: str) -> bool:
    return host == candidate or host.endswith("." + candidate)


def platform_from_extractor(extractor_key: str) -> str:
    key = str(extractor_key or "").strip().lower()
    if not key:
        return "generic_web"
    if key in EXTRACTOR_ALIASES:
        return EXTRACTOR_ALIASES[key]
    if ":" in key:
        prefix = key.split(":", 1)[0]
        if prefix in EXTRACTOR_ALIASES:
            return EXTRACTOR_ALIASES[prefix]
        return prefix
    return key


def platform_from_host(host: str) -> str:
    normalized = str(host or "").lower().removeprefix("www.")
    for platform, hosts in PLATFORM_HOSTS.items():
        if any(_matches_host(normalized, item) for item in hosts):
            return platform
    return "generic_web"


def source_family(platform: str) -> str:
    value = str(platform or "generic_web").lower()
    for family, platforms in SOURCE_FAMILIES.items():
        if value in platforms:
            return family
    return "generic"


def universal_capabilities() -> Dict[str, Any]:
    """Return a stable, serializable description of Phase 8 source coverage."""
    platforms = sorted(
        {
            platform
            for family in SOURCE_FAMILIES.values()
            if family != ("generic_web",)
            for platform in family
        }
        | set(PLATFORM_HOSTS)
    )
    return {
        "universal_sources": True,
        "source_families": {
            family: list(platforms)
            for family, platforms in SOURCE_FAMILIES.items()
        },
        "platforms": platforms,
        "generic_web_fallback": True,
        "extractor_driven_discovery": True,
        "local_files": True,
        "direct_media_urls": True,
        "streaming_urls": True,
        "note": "Platform names are recognition hints; actual access depends on the active extractor, authentication, DRM, geo restrictions, and source availability.",
    }


def is_media_url_scheme(scheme: str) -> bool:
    return str(scheme or "").lower() in MEDIA_URL_SCHEMES


def is_direct_media_extension(extension: str) -> bool:
    return str(extension or "").lower() in DIRECT_MEDIA_EXTENSIONS


def iter_platforms() -> Iterable[str]:
    return iter(universal_capabilities()["platforms"])
