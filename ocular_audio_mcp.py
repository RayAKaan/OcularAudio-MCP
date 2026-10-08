import os
import re
import sys
import json
import tempfile
import time
import asyncio
import subprocess
import http.cookiejar
import logging
import threading
from pathlib import Path
from functools import lru_cache

# Python version check (list[int] requires 3.9+)
if sys.version_info < (3, 9):
    sys.exit("Error: OcularAudio MCP requires Python 3.9 or higher. You are running Python {}.{}".format(*sys.version_info[:2]))

from requests import Session
from mcp.server.fastmcp import FastMCP, Image
from youtube_transcript_api import YouTubeTranscriptApi
import yt_dlp
import cv2

from media_resolver import (
    normalize_analysis_level,
    resolve_media_source,
    stable_source_id,
    classify_source,
)
from evidence_index import (
    build_evidence_segments,
    format_timestamp,
    nearest_evidence,
    search_evidence,
    timeline_window,
)
from visual_index import (
    frame_descriptor,
    frames_from_payload,
    normalize_crop_box,
    sample_timestamps,
    search_visual_frames,
    select_burst_timestamps,
)

__version__ = "1.5.0"

# Configure logging to stderr so it does NOT corrupt the MCP stdio protocol
logging.basicConfig(
    level=logging.INFO,
    format="[%(levelname)s] %(message)s",
    stream=sys.stderr,
)
log = logging.getLogger("ocular_audio_mcp")

# Define cache and config directories
CACHE_DIR = Path(os.path.expanduser("~")) / ".cache" / "ocular_audio_mcp"
CACHE_DIR.mkdir(parents=True, exist_ok=True)
VISUAL_CACHE_DIR = CACHE_DIR / "visual"
VISUAL_CACHE_DIR.mkdir(parents=True, exist_ok=True)
VISUAL_FRAME_DIR = VISUAL_CACHE_DIR / "frames"
VISUAL_FRAME_DIR.mkdir(parents=True, exist_ok=True)
VISUAL_INDEX_VERSION = 1
VISUAL_MAX_FRAMES = 240

# Cache expiration: 7 days in seconds
CACHE_MAX_AGE = 7 * 24 * 60 * 60

# Timeout for blocking network operations (seconds)
NETWORK_TIMEOUT = 300

# Initialize the Model Context Protocol (MCP) server
mcp = FastMCP(
    "OcularAudio Server",
    dependencies=["youtube-transcript-api", "yt-dlp", "opencv-python-headless"]
)

# Global holder for the local whisper model instance (loaded lazily)
_whisper_engine = None
_whisper_lock = threading.Lock()


def _check_system_capabilities() -> dict:
    """Check availability of system dependencies and return capabilities."""
    capabilities = {
        "python_version": f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}",
        "ocular_audio_version": __version__,
        "supported_analysis_levels": ["glance", "understand", "deep", "omniscient"],
        "supported_source_types": ["web_url", "local_file", "direct_media_url", "live_url"],
        "ffmpeg": False,
        "whisper": {"available": False, "engine": None, "model_size": None},
        "tesseract": {"available": False, "path": None},
        "opencv": False,
        "cookies_found": False,
        "cache_dir": str(CACHE_DIR),
        "visual_evidence": {
            "available": True,
            "cache_dir": str(VISUAL_CACHE_DIR),
            "max_frames_per_index": VISUAL_MAX_FRAMES,
            "ocr_search": True,
        },
    }

    # Check FFmpeg
    try:
        result = subprocess.run(
            ["ffmpeg", "-version"],
            capture_output=True,
            timeout=5,
            creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == 'win32' else 0
        )
        capabilities["ffmpeg"] = result.returncode == 0
    except (FileNotFoundError, subprocess.TimeoutExpired):
        capabilities["ffmpeg"] = False

    # Check Whisper engines
    try:
        from faster_whisper import WhisperModel
        model_size = os.environ.get("WHISPER_MODEL_SIZE", "tiny")
        capabilities["whisper"] = {
            "available": True,
            "engine": "faster-whisper",
            "model_size": model_size
        }
    except ImportError:
        try:
            import whisper
            model_size = os.environ.get("WHISPER_MODEL_SIZE", "tiny")
            capabilities["whisper"] = {
                "available": True,
                "engine": "openai-whisper",
                "model_size": model_size
            }
        except ImportError:
            capabilities["whisper"] = {"available": False, "engine": None, "model_size": None}

    # Check Tesseract
    try:
        import pytesseract
        if sys.platform == 'win32':
            tesseract_path = r'C:\Program Files\Tesseract-OCR\tesseract.exe'
            if os.path.exists(tesseract_path):
                capabilities["tesseract"] = {"available": True, "path": tesseract_path}
            else:
                # Try to find in PATH
                try:
                    result = subprocess.run(
                        ["tesseract", "--version"],
                        capture_output=True,
                        timeout=5,
                        creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == 'win32' else 0
                    )
                    if result.returncode == 0:
                        capabilities["tesseract"] = {"available": True, "path": "tesseract (in PATH)"}
                except (FileNotFoundError, subprocess.TimeoutExpired):
                    capabilities["tesseract"] = {"available": False, "path": None}
        else:
            # macOS/Linux - check PATH
            try:
                result = subprocess.run(
                    ["tesseract", "--version"],
                    capture_output=True,
                    timeout=5
                )
                if result.returncode == 0:
                    capabilities["tesseract"] = {"available": True, "path": "tesseract (in PATH)"}
            except (FileNotFoundError, subprocess.TimeoutExpired):
                capabilities["tesseract"] = {"available": False, "path": None}
    except ImportError:
        capabilities["tesseract"] = {"available": False, "path": None}

    # Check OpenCV
    try:
        import cv2
        capabilities["opencv"] = True
    except ImportError:
        capabilities["opencv"] = False

    # Check cookies
    capabilities["cookies_found"] = bool(find_cookies_file())

    return capabilities


def _get_cache_list() -> list:
    """List all cached videos with metadata."""
    cache_files = list(CACHE_DIR.glob("*.json"))
    videos = []
    for cache_file in cache_files:
        try:
            data = json.loads(cache_file.read_text(encoding='utf-8'))
            meta = data.get("metadata", {})
            stat = cache_file.stat()
            videos.append({
                "id": cache_file.stem,
                "title": meta.get("title", "Unknown"),
                "uploader": meta.get("uploader", "Unknown"),
                "duration": meta.get("duration", "Unknown"),
                "method": data.get("method", "unknown"),
                "cached_at": data.get("timestamp", 0),
                "file_size_bytes": stat.st_size,
            })
        except Exception:
            videos.append({
                "id": cache_file.stem,
                "title": "(corrupted)",
                "uploader": "",
                "duration": "Unknown",
                "method": "unknown",
                "cached_at": 0,
                "file_size_bytes": cache_file.stat().st_size,
            })
    return sorted(videos, key=lambda x: x.get("cached_at", 0), reverse=True)


def _clear_cache(video_id: str = None) -> dict:
    """Clear cache for a specific video or all videos."""
    if video_id:
        cache_file = CACHE_DIR / f"{video_id}.json"
        if cache_file.exists():
            cache_file.unlink()
            return {"cleared": 1, "video_id": video_id}
        return {"cleared": 0, "video_id": video_id, "message": "Not found in cache"}
    else:
        count = len(list(CACHE_DIR.glob("*.json")))
        for f in CACHE_DIR.glob("*.json"):
            f.unlink()
        return {"cleared": count, "message": f"Cleared {count} cached videos"}

def get_whisper_engine():
    global _whisper_engine
    with _whisper_lock:
        if _whisper_engine is not None:
            return _whisper_engine

        model_size = os.environ.get("WHISPER_MODEL_SIZE", "tiny")
        log.info("Initializing local transcription engine (model=%s)...", model_size)
        try:
            from faster_whisper import WhisperModel
            log.info("Using high-performance 'faster-whisper' engine.")
            _whisper_engine = {
                "type": "faster-whisper",
                "model": WhisperModel(model_size, device="cpu", compute_type="int8")
            }
            return _whisper_engine
        except ImportError as e:
            log.debug("faster-whisper not available: %s", e)

        try:
            import whisper
            log.info("Using standard 'openai-whisper' engine.")
            _whisper_engine = {
                "type": "openai-whisper",
                "model": whisper.load_model(model_size)
            }
            return _whisper_engine
        except ImportError as e:
            log.debug("openai-whisper not available: %s", e)
            raise ImportError(
                "No local ASR engines found. Please install one of the following:\n"
                "  pip install faster-whisper\n"
                "  pip install openai-whisper torch"
            )


def find_cookies_file() -> str:
    """Search for cookies.txt in known locations.

    Search order:
      1. ~/.cache/ocular_audio_mcp/cookies.txt
      2. ~/.config/ocular_audio_mcp/cookies.txt
      3. ./cookies.txt (relative to current working directory)
    """
    search_paths = [
        CACHE_DIR / "cookies.txt",
        Path(os.path.expanduser("~")) / ".config" / "ocular_audio_mcp" / "cookies.txt",
        Path("./cookies.txt"),
    ]
    for path in search_paths:
        if path.exists():
            log.info("Found cookies file at: %s", path)
            return str(path)
    return ""


def get_authenticated_session(cookies_path: str) -> Session:
    session = Session()
    session.headers.update({
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
    })
    if cookies_path:
        try:
            cookie_jar = http.cookiejar.MozillaCookieJar(cookies_path)
            cookie_jar.load(ignore_discard=True, ignore_expires=True)
            session.cookies = cookie_jar
            log.info("Successfully loaded cookies into request session.")
        except Exception as e:
            log.warning("Failed to load cookies from %s: %s", cookies_path, e)
    return session


def extract_video_id(url: str) -> str:
    patterns = [
        r'(?:v=|\/embed\/|\/v\/|youtu\.be\/)([0-9A-Za-z_-]{11})(?:\b|[&?/])',
    ]
    for pattern in patterns:
        match = re.search(pattern, url)
        if match:
            return match.group(1)
    return ""


def _cache_id(url: str) -> str:
    """Generate a collision-resistant cache ID for any supported media source."""
    return stable_source_id(url)


def _default_metadata(cache_id: str) -> dict:
    """Return a default metadata dict when fetch fails."""
    return {
        "title": f"Web Video (ID: {cache_id})",
        "uploader": "Unknown",
        "views": 0,
        "duration": "N/A",
        "upload_date": "N/A",
        "chapters": []
    }


def _blocking_metadata_fetch(url: str, cookies_path: str) -> dict:
    source = resolve_media_source(url, cookies_path)
    if source.get("source_kind") == "local_file":
        duration = source.get("duration_seconds")
        duration_str = "Unknown"
        if duration:
            total = int(duration)
            duration_str = f"{total // 3600}h {((total % 3600) // 60)}m {total % 60}s" if total >= 3600 else f"{total // 60}m {total % 60}s"
        return {
            "title": source.get("title") or Path(source["source"]).stem,
            "uploader": "",
            "views": 0,
            "duration": duration_str,
            "upload_date": "N/A",
            "chapters": [],
            "source": source,
        }
    ydl_opts = {
        'quiet': True,
        'no_warnings': True,
        'socket_timeout': 30,
    }
    if cookies_path:
        ydl_opts['cookiefile'] = cookies_path

    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(url, download=False)

        raw_chapters = info.get("chapters", [])
        formatted_chapters = []
        if raw_chapters:
            for idx, chap in enumerate(raw_chapters, 1):
                start = int(chap.get("start_time", 0))
                start_min = start // 60
                start_sec = start % 60
                formatted_chapters.append(
                    f"• [{start_min:02d}:{start_sec:02d}] Chapter {idx}: {chap.get('title', 'Untitled')}"
                )

        duration_secs = info.get("duration", 0)
        if duration_secs:
            minutes = duration_secs // 60
            seconds = duration_secs % 60
            duration_str = f"{minutes}m {seconds}s"
        else:
            duration_str = "Unknown"

        has_audio = any(f.get("acodec") not in (None, "none") for f in info.get("formats", []))
        has_video = any(f.get("vcodec") not in (None, "none") for f in info.get("formats", []))
        has_captions = bool(info.get("subtitles") or info.get("automatic_captions"))
        return {
            "title": info.get("title") or "Unknown Title",
            "uploader": info.get("uploader") or "Unknown Creator",
            "views": info.get("view_count") or 0,
            "duration": duration_str,
            "upload_date": info.get("upload_date") or "N/A",
            "chapters": formatted_chapters,
            "source": {
                "source_id": stable_source_id(url),
                "source_kind": "url",
                "platform": source.get("platform", "generic_web"),
                "extractor": info.get("extractor_key") or info.get("extractor"),
                "media_type": "video" if has_video else "audio" if has_audio else "unknown",
                "is_live": bool(info.get("is_live")),
                "has_audio": has_audio,
                "has_video": has_video,
                "has_captions": has_captions,
                "capabilities": {
                    "metadata": True, "audio": has_audio, "video": has_video,
                    "captions": has_captions, "screenshots": has_video,
                    "live": bool(info.get("is_live")),
                },
            },
        }


def format_seconds(seconds: float) -> str:
    minutes = int(seconds) // 60
    secs = int(seconds) % 60
    return f"[{minutes:02d}:{secs:02d}]"


def extract_key_timestamps(transcript: str, duration_secs: int, mode: str = "balanced") -> list[tuple[int, str, int]]:
    """Analyze transcript and return key visual timestamps.

    Returns list of (timestamp_secs, reason, score) tuples, sorted by timestamp.
    Uses percentile-based selection for meaningful differentiation between modes.
    """
    lines = transcript.strip().split('\n')
    segments = []
    for line in lines:
        match = re.match(r'\[(\d+):(\d+)\]\s*(.*)', line)
        if match:
            ts = int(match.group(1)) * 60 + int(match.group(2))
            text = match.group(3).strip()
            if text:
                segments.append((ts, text))

    if not segments:
        return []

    scored = []
    for i, (ts, text) in enumerate(segments):
        score = 0
        reasons = []
        lower = text.lower()

        # === HIGH VALUE (5 points) ===
        has_numbers = bool(re.search(r'\$\d+|₹\d+|\d+[\.,]?\d*\s*(%|percent|lakh|crore|k\b|m\b|billion|million)', text))
        has_context = bool(re.search(r'(chart|graph|table|breakdown|compare|vs|versus|difference|average|total|revenue|profit|salary|cost|price|income|earn)', lower))

        strong_cues = ['look at this', 'as you can see', 'check this out', 'let me show you',
                       'right here', 'you can see', 'see this', 'notice this', 'observe this',
                       'this is what', 'look here', 'see here']
        has_visual_cue = False
        for cue in strong_cues:
            if cue in lower:
                has_visual_cue = True
                break

        if has_numbers and has_context:
            score += 5
            reasons.append("numbers + context (chart/table likely)")
        elif has_numbers and has_visual_cue:
            score += 5
            reasons.append("visual cue + numbers confirmed")
        elif has_numbers:
            score += 3
            reasons.append("numbers/data detected")
        elif has_visual_cue:
            score += 2
            reasons.append('visual cue (preview)')

        # === MEDIUM VALUE (2-3 points) ===
        comparisons = ['before vs after', 'difference between', 'compared to', 'versus',
                       'expectation vs reality', 'vs', 'v/s', 'compare']
        for comp in comparisons:
            if comp in lower:
                score += 3
                reasons.append(f"comparison: {comp}")
                break

        if re.search(r'\b(first|second|third|fourth|fifth|number one|number two|number three)\b', lower):
            score += 2
            reasons.append("numbered list")
        if re.search(r'\bstep\s*\d|point\s*\d|\d\)', lower):
            score += 2
            reasons.append("step/list")

        emphasis = ['important', 'remember', 'key point', 'note that', 'keep in mind',
                    'crucial', 'essential', 'must know', 'biggest mistake', 'watch out']
        for phrase in emphasis:
            if phrase in lower:
                score += 2
                reasons.append(f"emphasis: {phrase}")
                break

        # === LOW VALUE (1 point) ===
        if i < len(segments) - 1:
            next_ts = segments[i + 1][0]
            if next_ts - ts > 10:
                score += 1
                reasons.append("topic transition")

        if text.isupper() and len(text) > 5:
            score += 1
            reasons.append("emphasized")
        if '!' in text:
            score += 1
            reasons.append("excited")

        if i < len(segments) - 1:
            seg_duration = segments[i + 1][0] - ts
            if seg_duration > 15:
                score += 1
                reasons.append("extended")

        if ts < 10:
            score += 1
            reasons.append("opening")
        if duration_secs > 0 and ts > duration_secs - 30:
            score += 1
            reasons.append("closing")

        if i > 0:
            prev_ts = segments[i - 1][0]
            if ts - prev_ts > 5:
                score += 1
                reasons.append("scene change")

        if score > 0:
            reason_str = "; ".join(reasons)
            scored.append((ts, reason_str, score))

    if not scored:
        return []

    # Cluster merging: compare against FIRST item to prevent unbounded growth
    clusters = []
    current_cluster = [scored[0]]
    for item in scored[1:]:
        if item[0] - current_cluster[0][0] <= 15:
            current_cluster.append(item)
        else:
            clusters.append(current_cluster)
            current_cluster = [item]
    clusters.append(current_cluster)

    # Pick highest-scoring from each cluster
    best_per_cluster = []
    for cluster in clusters:
        best = max(cluster, key=lambda x: x[2])
        best_per_cluster.append(best)

    # Sort by score descending for percentile calculation
    best_per_cluster.sort(key=lambda x: x[2], reverse=True)

    # Apply percentile-based selection
    total = len(best_per_cluster)
    MAX_SCREENSHOTS = 50

    if mode == "overview":
        filtered = []
    elif mode == "deep":
        cutoff = max(1, min(int(total * 0.75), MAX_SCREENSHOTS))
        filtered = best_per_cluster[:cutoff]
    elif mode == "balanced":
        cutoff = max(1, min(int(total * 0.25), MAX_SCREENSHOTS))
        filtered = best_per_cluster[:cutoff]
    elif mode == "auto":
        minutes = duration_secs / 60 if duration_secs > 0 else 10
        if minutes < 5:
            cutoff = max(1, min(int(total * 0.50), MAX_SCREENSHOTS))
        elif minutes < 30:
            cutoff = max(1, min(int(total * 0.30), MAX_SCREENSHOTS))
        else:
            cutoff = max(1, min(int(total * 0.20), MAX_SCREENSHOTS))
        filtered = best_per_cluster[:cutoff]
    else:
        log.warning("Unknown mode '%s', falling back to 'auto'", mode)
        minutes = duration_secs / 60 if duration_secs > 0 else 10
        cutoff = max(1, min(int(total * 0.30), MAX_SCREENSHOTS))
        filtered = best_per_cluster[:cutoff]

    # Sort filtered results by timestamp for chronological order
    filtered.sort(key=lambda x: x[0])

    log.info("Timestamp analysis: %d segments, %d clusters, %d scored, %d selected (mode=%s)",
             len(segments), len(clusters), total, len(filtered), mode)
    return filtered


def read_from_cache(video_id: str) -> dict:
    cache_path = CACHE_DIR / f"{video_id}.json"
    if cache_path.exists():
        try:
            # Check cache age
            age = time.time() - cache_path.stat().st_mtime
            if age > CACHE_MAX_AGE:
                log.info("Cache expired for %s (%.0f days old)", video_id, age / 86400)
                cache_path.unlink(missing_ok=True)
                return None

            # Check file size (10MB limit)
            if cache_path.stat().st_size > 10 * 1024 * 1024:
                log.warning("Cache file too large for %s, removing", video_id)
                cache_path.unlink(missing_ok=True)
                return None

            with open(cache_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except json.JSONDecodeError as e:
            log.warning("Corrupted cache for %s, removing: %s", video_id, e)
            cache_path.unlink(missing_ok=True)
        except Exception as e:
            log.warning("Cache read failed for %s: %s", video_id, e)
    return None


def write_to_cache(video_id: str, data: dict) -> bool:
    cache_path = CACHE_DIR / f"{video_id}.json"
    try:
        # Atomic write: write to temp file, then rename
        tmp_fd, tmp_path = tempfile.mkstemp(dir=CACHE_DIR, suffix='.tmp')
        try:
            with os.fdopen(tmp_fd, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            os.replace(tmp_path, cache_path)
            return True
        except Exception:
            os.unlink(tmp_path)
            raise
    except Exception as e:
        log.warning("Failed to write cache for %s: %s", video_id, e)
        return False


def _blocking_whisper_transcription(url_or_id: str, cookies_path: str) -> str:
    engine = get_whisper_engine()
    temp_dir = tempfile.gettempdir()

    sanitized_id = "".join([c if c.isalnum() else "_" for c in url_or_id[-11:]])
    audio_template = os.path.join(temp_dir, f"yt_audio_{sanitized_id}.%(ext)s")

    ydl_opts = {
        'format': 'bestaudio/best',
        'outtmpl': audio_template,
        'postprocessors': [{
            'key': 'FFmpegExtractAudio',
            'preferredcodec': 'mp3',
            'preferredquality': '128',
        }],
        'quiet': True,
        'no_warnings': True,
        'socket_timeout': 30,
    }
    if cookies_path:
        ydl_opts['cookiefile'] = cookies_path

    local_source = Path(os.path.expanduser(url_or_id))
    is_local_file = local_source.exists() and local_source.is_file()

    if is_local_file:
        audio_file_path = os.path.join(temp_dir, f"ocular_audio_{sanitized_id}.mp3")
        log.info("PROGRESS: Extracting audio from local media...")
        result = subprocess.run(
            ["ffmpeg", "-y", "-i", str(local_source), "-vn", "-acodec", "libmp3lame", "-b:a", "128k", audio_file_path],
            capture_output=True, text=True, timeout=NETWORK_TIMEOUT
        )
        if result.returncode != 0:
            raise RuntimeError("Failed to extract audio from local media with FFmpeg.")
    else:
        download_target = url_or_id if url_or_id.startswith("http") else f"https://www.youtube.com/watch?v={url_or_id}"
        log.info("PROGRESS: Downloading audio track for transcription...")
        log.info("Starting audio track extraction for %s via yt-dlp...", download_target)
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.download([download_target])

        audio_file_path = os.path.join(temp_dir, f"yt_audio_{sanitized_id}.mp3")

    if not os.path.exists(audio_file_path):
        raise FileNotFoundError(
            "Audio track download failed. Possible causes:\n"
            "  - Network error or video is geo-blocked\n"
            "  - Video requires authentication (try adding cookies.txt)\n"
            "  - FFmpeg is not installed or not in PATH"
        )

    log.info("PROGRESS: Running Whisper speech-to-text locally...")
    log.info("Running Whisper speech-to-text offline locally...")
    formatted_segments = []

    try:
        if engine["type"] == "faster-whisper":
            segments, info = engine["model"].transcribe(audio_file_path, beam_size=3)
            for segment in segments:
                timestamp = format_seconds(segment.start)
                formatted_segments.append(f"{timestamp} {segment.text.strip()}")
        else:
            result = engine["model"].transcribe(audio_file_path)
            segments = result.get("segments", [])
            for seg in segments:
                timestamp = format_seconds(seg.get("start", 0))
                formatted_segments.append(f"{timestamp} {seg.get('text', '').strip()}")
    finally:
        try:
            os.remove(audio_file_path)
        except OSError:
            pass

    return "\n".join(formatted_segments)


@mcp.tool()
async def get_ocular_audio_transcript(url: str, use_local_whisper: bool = True) -> str:
    """
    Extracts the complete transcript, video chapters, and metadata of any YouTube or general Web video.

    This is an advanced, fully asynchronous, production-grade hybrid engine:
    1. Checks local cache first (instantaneous, 0.01s).
    2. Fetches subtitles asynchronously with cookie-authentication (works primarily on YouTube).
    3. Falls back to local Whisper transcription running in a background executor thread
       for general web videos (Vimeo, Twitter, etc.) or YouTube videos without captions.

    Args:
        url: The full YouTube or Web video URL.
        use_local_whisper: Enable offline local transcribing fallback if subtitles are missing.
    """
    video_id = extract_video_id(url)
    is_youtube = bool(video_id)

    cache_id = _cache_id(url)
    cookies_path = find_cookies_file()

    # 1. CHECK CACHE FIRST
    cached_data = read_from_cache(cache_id)
    if cached_data:
        log.info("Cache hit for %s. Loading transcript.", cache_id)
        header, transcript, _ = _build_transcript_text(cached_data=cached_data, url=url)
        return "[CACHE HIT: LOADED FROM LOCAL CACHE]\n" + header + transcript

    # 2. RUN METADATA FETCH
    log.info("PROGRESS: Fetching video metadata...")
    log.info("Fetching video metadata and chapters asynchronously...")
    try:
        metadata = await asyncio.wait_for(
            asyncio.to_thread(_blocking_metadata_fetch, url, cookies_path),
            timeout=NETWORK_TIMEOUT
        )
    except asyncio.TimeoutError:
        log.error("Metadata fetch timed out after %ds", NETWORK_TIMEOUT)
        metadata = _default_metadata(cache_id)
    except Exception as e:
        log.warning("yt-dlp metadata fetch failed: %s", e)
        metadata = _default_metadata(cache_id)

    # 3. APPROACH 1: Fast Subtitle API (Only works on YouTube)
    if is_youtube:
        try:
            log.info("PROGRESS: Fetching YouTube captions...")
            log.info("Querying YouTube caption endpoints...")
            session = get_authenticated_session(cookies_path)

            def fetch_captions():
                api = YouTubeTranscriptApi(http_client=session)
                return api.fetch(video_id)

            transcript_list = await asyncio.wait_for(
                asyncio.to_thread(fetch_captions),
                timeout=NETWORK_TIMEOUT
            )

            formatted_segments = []
            for entry in transcript_list:
                timestamp = format_seconds(entry.start)
                formatted_segments.append(f"{timestamp} {entry.text}")

            transcript_text = "\n".join(formatted_segments)

            write_to_cache(cache_id, {
                "metadata": metadata,
                "transcript": transcript_text,
                "method": "official_captions",
                "timestamp": time.time()
            })

            header, _, _ = _build_transcript_text(metadata=metadata, url=url)
            return "[SUCCESS: YouTube Captions]\n" + header + transcript_text
        except Exception as caption_error:
            log.info("Caption API unavailable, falling back to Whisper. Details: %s", caption_error)

    # 4. APPROACH 2: Local Audio Download + Local Whisper ASR
    if not use_local_whisper:
        return (
            f"Error: No captions available for this video, and Whisper fallback is disabled.\n"
            f"Video Title: {metadata.get('title', 'Unknown')}\n"
            f"Video Uploader: {metadata.get('uploader', 'Unknown')}\n"
            f"Suggestion: Re-run with use_local_whisper=True, or add a cookies.txt file for age-restricted videos."
        )

    try:
        log.info("Starting local offline Whisper ASR in background thread...")
        target_param = video_id if is_youtube else url
        transcript_text = await asyncio.wait_for(
            asyncio.to_thread(_blocking_whisper_transcription, target_param, cookies_path),
            timeout=NETWORK_TIMEOUT
        )

        write_to_cache(cache_id, {
            "metadata": metadata,
            "transcript": transcript_text,
            "method": "local_whisper_fallback",
            "timestamp": time.time()
        })

        header, _, _ = _build_transcript_text(metadata=metadata, url=url)
        return "[SUCCESS: Offline Local ASR Transcription]\n" + header + transcript_text

    except asyncio.TimeoutError:
        log.error("Whisper transcription timed out after %ds", NETWORK_TIMEOUT)
        return (
            f"Error: Transcription timed out after {NETWORK_TIMEOUT} seconds.\n"
            f"Video Title: {metadata.get('title', 'Unknown')}\n"
            f"Suggestion: Try a shorter video or check your network connection."
        )
    except ImportError as e:
        log.error("Whisper engine not installed: %s", e)
        return (
            f"Error: Local transcription engine is not installed.\n"
            f"Details: {str(e)}\n"
            f"Please install one of the following:\n"
            f"  pip install faster-whisper\n"
            f"  pip install openai-whisper torch"
        )
    except Exception as whisper_error:
        log.error("Whisper transcription failed: %s", whisper_error)
        return (
            f"Error: Local offline transcription failed.\n"
            f"Details: {str(whisper_error)}\n"
            f"Troubleshooting:\n"
            f"  - Ensure FFmpeg is installed and in your PATH\n"
            f"  - Check your network connection\n"
            f"  - For age-restricted videos, add a cookies.txt file"
        )


def extract_text_from_frame(image_path: str) -> str:
    """Run OCR on a captured frame using Tesseract with OpenCV preprocessing.

    Returns extracted text or empty string if Tesseract is not installed.
    """
    try:
        import pytesseract
    except ImportError:
        log.warning("pytesseract not installed. OCR skipped. Install: pip install pytesseract")
        return ""

    try:
        # Auto-detect Tesseract on Windows if not in PATH
        if sys.platform == 'win32':
            tesseract_path = r'C:\Program Files\Tesseract-OCR\tesseract.exe'
            if os.path.exists(tesseract_path):
                pytesseract.pytesseract.tesseract_cmd = tesseract_path

        img = cv2.imread(image_path)
        if img is None:
            return ""

        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        thresh = cv2.adaptiveThreshold(
            gray, 255,
            cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
            cv2.THRESH_BINARY, 11, 2
        )
        text = pytesseract.image_to_string(thresh, config='--psm 6')
        # Sanitize output to avoid encoding errors
        return text.encode('ascii', errors='ignore').decode('ascii').strip()
    except Exception as e:
        log.warning("OCR failed on %s: %s", image_path, e)
        return ""


def _blocking_screenshot_extractor(url: str, timestamps_secs: list[int], cookies_path: str, enable_ocr: bool = False) -> list:
    source = classify_source(url)
    is_local_file = source.get("source_kind") == "local_file"
    is_youtube = bool(extract_video_id(url))
    stream_url = source.get("source") if is_local_file else None

    if not is_local_file:
        try:
            ydl_opts = {
                "format": "18" if is_youtube else "best",
                "quiet": True,
                "no_warnings": True,
                "socket_timeout": 30,
                "noplaylist": True,
            }
            if cookies_path:
                ydl_opts["cookiefile"] = cookies_path

            log.info("Extracting streaming source URL...")
            log.info("PROGRESS: Connecting to video source...")
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=False)
                stream_url = info.get("url")
                if not stream_url:
                    for fmt in info.get("formats", []):
                        if fmt.get("url") and fmt.get("vcodec") != "none":
                            stream_url = fmt["url"]
                            break
        except Exception as exc:
            log.warning("yt-dlp stream extraction failed: %s. Falling back to direct URL streaming.", exc)
            stream_url = url

    if not stream_url:
        stream_url = url

    log.info("PROGRESS: Opening video stream with OpenCV...")
    log.info("Connecting OpenCV to stream URL: %s...", str(stream_url)[:60])
    cap = cv2.VideoCapture(stream_url)

    try:
        if not cap.isOpened():
            return [
                "Error: Failed to open video stream with OpenCV.\n"
                "Possible causes:\n"
                "  - Video is no longer available\n"
                "  - Network connection issue\n"
                "  - FFmpeg codecs missing"
            ]

        fps = cap.get(cv2.CAP_PROP_FPS)
        total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        log.info("Stream details: FPS=%s, Total Frames=%s", fps, total_frames)

        if fps <= 0 or total_frames <= 0:
            log.warning("Stream reported 0 FPS or 0 total frames. Using defaults.")
            fps = 25.0
            total_frames = 5000

        temp_dir = tempfile.gettempdir()
        cache_id = _cache_id(url)
        success_count = 0
        payload = []

        for idx, sec in enumerate(sorted(timestamps_secs), 1):
            target_frame_idx = int(sec * fps)
            log.info("PROGRESS: Capturing frame %d/%d at %ss...", idx, len(timestamps_secs), sec)

            if target_frame_idx >= total_frames:
                payload.append(f"[WARNING: Requested timestamp {sec}s is beyond the end of the video.]")
                continue

            cap.set(cv2.CAP_PROP_POS_FRAMES, target_frame_idx)
            ret, frame = cap.read()

            if ret:
                resized_frame = cv2.resize(frame, (640, 360))
                temp_img_path = os.path.join(temp_dir, f"mcp_seek_{cache_id}_{sec}s.jpg")
                cv2.imwrite(temp_img_path, resized_frame)
                payload.append(Image(path=temp_img_path))

                if enable_ocr:
                    ocr_text = extract_text_from_frame(temp_img_path)
                    if ocr_text:
                        payload.append(f"[OCR at {sec}s]:\n{ocr_text}")

                success_count += 1
            else:
                payload.append(f"[WARNING: Failed to seek or read frame at {sec} seconds.]")

        return [
            f"[SUCCESS: Screenshot Extraction Completed]\n"
            f"Successfully captured {success_count} of {len(timestamps_secs)} requested frames.\n"
            f"The image content blocks are attached below in chronological order."
        ] + payload
    finally:
        cap.release()


@mcp.tool()
async def get_ocular_audio_video_screenshots(url: str, timestamps_secs: list[int], enable_ocr: bool = False) -> list:
    """
    Extracts high-quality, low-resolution screenshots at specific timestamps directly from any YouTube or Web video
    WITHOUT downloading the entire file (uses HTTP range-seeking streaming).

    This runs asynchronously in a background thread to prevent blocking concurrent MCP requests.

    Args:
        url: The full YouTube or Web video URL.
        timestamps_secs: A list of timestamps in seconds to screenshot (e.g., [45, 120, 300])
        enable_ocr: If True, run OCR on each captured frame to extract visible text.
    """
    cookies_path = find_cookies_file()

    try:
        payload = await asyncio.wait_for(
            asyncio.to_thread(_blocking_screenshot_extractor, url, timestamps_secs, cookies_path, enable_ocr),
            timeout=NETWORK_TIMEOUT
        )
        return payload
    except asyncio.TimeoutError:
        return [f"Error: Screenshot extraction timed out after {NETWORK_TIMEOUT} seconds."]
    except Exception as e:
        return [f"Error during screenshot extraction: {str(e)}"]


def _visual_index_path(cache_id: str) -> Path:
    return VISUAL_CACHE_DIR / f"{cache_id}.json"


def _visual_frame_dir(cache_id: str) -> Path:
    path = VISUAL_FRAME_DIR / cache_id
    path.mkdir(parents=True, exist_ok=True)
    return path


def _read_visual_index(cache_id: str) -> dict | None:
    path = _visual_index_path(cache_id)
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def _write_visual_index(cache_id: str, payload: dict) -> None:
    path = _visual_index_path(cache_id)
    temp = path.with_suffix(".tmp")
    temp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(temp, path)


def _blocking_visual_frame_capture(
    url: str,
    timestamps_secs: list[int],
    cookies_path: str,
    enable_ocr: bool = False,
) -> list[dict]:
    """Capture persistent, higher-fidelity frames for the Phase 3 visual index."""
    source = classify_source(url)
    is_local_file = source.get("source_kind") == "local_file"
    stream_url = source.get("source") if is_local_file else None

    if not is_local_file:
        try:
            ydl_opts = {
                "format": "bestvideo[ext=mp4]/best[ext=mp4]/best",
                "quiet": True,
                "no_warnings": True,
                "socket_timeout": 30,
                "noplaylist": True,
            }
            if cookies_path:
                ydl_opts["cookiefile"] = cookies_path
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=False)
                stream_url = info.get("url")
                if not stream_url:
                    for fmt in info.get("formats", []):
                        if fmt.get("url") and fmt.get("vcodec") != "none":
                            stream_url = fmt["url"]
                            break
        except Exception as exc:
            log.warning("Visual stream resolution failed: %s", exc)
            stream_url = url

    cap = cv2.VideoCapture(stream_url or url)
    if not cap.isOpened():
        cap.release()
        raise RuntimeError("Failed to open video stream for visual evidence.")

    try:
        fps = cap.get(cv2.CAP_PROP_FPS)
        total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        if fps <= 0:
            fps = 25.0

        cache_id = _cache_id(url)
        output_dir = _visual_frame_dir(cache_id)
        results = []
        for index, sec in enumerate(sorted(set(max(0, int(t)) for t in timestamps_secs)), 1):
            target_frame = int(sec * fps)
            if total_frames > 0 and target_frame >= total_frames:
                continue
            cap.set(cv2.CAP_PROP_POS_FRAMES, target_frame)
            ok, frame = cap.read()
            if not ok:
                continue

            height, width = frame.shape[:2]
            max_dimension = 1280
            if max(width, height) > max_dimension:
                scale = max_dimension / max(width, height)
                frame = cv2.resize(
                    frame,
                    (max(1, int(width * scale)), max(1, int(height * scale))),
                    interpolation=cv2.INTER_AREA,
                )

            image_path = output_dir / f"{sec:08d}.jpg"
            cv2.imwrite(str(image_path), frame, [int(cv2.IMWRITE_JPEG_QUALITY), 88])
            ocr_text = extract_text_from_frame(str(image_path)) if enable_ocr else ""
            descriptor = frame_descriptor(
                str(image_path),
                sec,
                f"f{sec:08d}",
                ocr_text,
            )
            results.append(descriptor.to_dict())
            log.info("PROGRESS: Indexed visual frame %d/%d at %ss...", index, len(timestamps_secs), sec)
        return results
    finally:
        cap.release()


@mcp.tool()
async def index_ocular_audio_video_visuals(
    url: str,
    interval_seconds: float = 10,
    enable_ocr: bool = True,
    force: bool = False,
) -> str:
    """Build or refresh a persistent timestamped visual evidence index for a media source."""
    try:
        cache_id = _cache_id(url)
        if not force:
            existing = _read_visual_index(cache_id)
            if existing and existing.get("version") == VISUAL_INDEX_VERSION:
                return json.dumps(existing, ensure_ascii=False, indent=2)

        resolved = await asyncio.wait_for(
            asyncio.to_thread(resolve_media_source, url, find_cookies_file()),
            timeout=NETWORK_TIMEOUT,
        )
        duration = float(resolved.get("duration_seconds") or 0)
        if duration <= 0:
            return json.dumps({
                "error": "Unable to determine media duration; visual indexing requires a finite video.",
                "source_id": cache_id,
            }, ensure_ascii=False)

        timestamps = sample_timestamps(
            duration,
            interval_seconds=interval_seconds,
            max_frames=VISUAL_MAX_FRAMES,
        )
        frames = await asyncio.wait_for(
            asyncio.to_thread(
                _blocking_visual_frame_capture,
                url,
                timestamps,
                find_cookies_file(),
                enable_ocr,
            ),
            timeout=NETWORK_TIMEOUT,
        )
        payload = {
            "version": VISUAL_INDEX_VERSION,
            "source_id": cache_id,
            "url": url,
            "title": resolved.get("title", ""),
            "duration_seconds": duration,
            "interval_seconds": max(1.0, float(interval_seconds)),
            "ocr_enabled": bool(enable_ocr),
            "frame_count": len(frames),
            "frames": frames,
            "created_at": time.time(),
        }
        _write_visual_index(cache_id, payload)
        return json.dumps(payload, ensure_ascii=False, indent=2)
    except asyncio.TimeoutError:
        return json.dumps({"error": "Visual indexing timed out."}, ensure_ascii=False)
    except Exception as exc:
        return json.dumps({"error": str(exc)}, ensure_ascii=False)


@mcp.tool()
async def search_ocular_audio_visuals(
    url: str,
    query: str,
    top_k: int = 8,
    min_score: float = 0.0,
) -> str:
    """Search indexed visual evidence using OCR text and return ranked frames."""
    cache_id = _cache_id(url)
    index = _read_visual_index(cache_id)
    if not index:
        return json.dumps({
            "error": "No visual index found.",
            "source_id": cache_id,
            "suggestion": "Run index_ocular_audio_video_visuals first.",
        }, ensure_ascii=False)
    frames = frames_from_payload(index.get("frames", []))
    results = search_visual_frames(frames, query, top_k=top_k, min_score=min_score)
    return json.dumps({
        "source_id": cache_id,
        "url": url,
        "query": query.strip(),
        "result_count": len(results),
        "results": [item.to_dict() for item in results],
    }, ensure_ascii=False, indent=2)


@mcp.tool()
async def get_ocular_audio_video_frame(
    url: str,
    timestamp_seconds: float,
    enable_ocr: bool = False,
) -> list:
    """Return one higher-resolution frame plus machine-readable frame metadata."""
    if timestamp_seconds < 0:
        return ["Error: timestamp_seconds must be >= 0."]
    try:
        payload = await asyncio.wait_for(
            asyncio.to_thread(
                _blocking_visual_frame_capture,
                url,
                [int(timestamp_seconds)],
                find_cookies_file(),
                enable_ocr,
            ),
            timeout=NETWORK_TIMEOUT,
        )
        if not payload:
            return [f"Error: Could not capture frame at {timestamp_seconds}s."]
        frame = payload[0]
        return [
            json.dumps(frame, ensure_ascii=False, indent=2),
            Image(path=frame["image_path"]),
        ]
    except asyncio.TimeoutError:
        return [f"Error: Frame extraction timed out after {NETWORK_TIMEOUT} seconds."]
    except Exception as exc:
        return [f"Error during frame extraction: {exc}"]


@mcp.tool()
async def get_ocular_audio_video_frame_burst(
    url: str,
    center_seconds: float,
    radius_seconds: float = 10,
    count: int = 5,
    enable_ocr: bool = False,
) -> list:
    """Return a bounded chronological burst of high-resolution frames around a moment."""
    if center_seconds < 0:
        return ["Error: center_seconds must be >= 0."]
    timestamps = select_burst_timestamps(center_seconds, radius_seconds, count)
    try:
        payload = await asyncio.wait_for(
            asyncio.to_thread(
                _blocking_visual_frame_capture,
                url,
                timestamps,
                find_cookies_file(),
                enable_ocr,
            ),
            timeout=NETWORK_TIMEOUT,
        )
        result = [
            json.dumps({
                "url": url,
                "center_seconds": center_seconds,
                "requested_timestamps": timestamps,
                "frame_count": len(payload),
                "frames": payload,
            }, ensure_ascii=False, indent=2)
        ]
        result.extend(Image(path=item["image_path"]) for item in payload)
        return result
    except asyncio.TimeoutError:
        return [f"Error: Frame burst extraction timed out after {NETWORK_TIMEOUT} seconds."]
    except Exception as exc:
        return [f"Error during frame burst extraction: {exc}"]


@mcp.tool()
async def crop_ocular_audio_video_frame(
    url: str,
    timestamp_seconds: float,
    x: float,
    y: float,
    width: float,
    height: float,
    normalized: bool = True,
    enable_ocr: bool = False,
) -> list:
    """Extract and crop a region from a timestamped frame using normalized or pixel coordinates."""
    if timestamp_seconds < 0:
        return ["Error: timestamp_seconds must be >= 0."]
    try:
        payload = await asyncio.wait_for(
            asyncio.to_thread(
                _blocking_visual_frame_capture,
                url,
                [int(timestamp_seconds)],
                find_cookies_file(),
                enable_ocr,
            ),
            timeout=NETWORK_TIMEOUT,
        )
        if not payload:
            return [f"Error: Could not capture frame at {timestamp_seconds}s."]
        frame_info = payload[0]
        image = cv2.imread(frame_info["image_path"])
        if image is None:
            return ["Error: Captured frame could not be read."]
        left, top, right, bottom = normalize_crop_box(
            x, y, width, height, image.shape[1], image.shape[0], normalized
        )
        crop = image[top:bottom, left:right]
        crop_path = Path(frame_info["image_path"]).with_name(
            Path(frame_info["image_path"]).stem + f"_crop_{left}_{top}_{right}_{bottom}.jpg"
        )
        cv2.imwrite(str(crop_path), crop, [int(cv2.IMWRITE_JPEG_QUALITY), 92])
        ocr_text = extract_text_from_frame(str(crop_path)) if enable_ocr else ""
        result = {
            **frame_info,
            "crop": {
                "x": left,
                "y": top,
                "width": right - left,
                "height": bottom - top,
                "normalized": normalized,
                "image_path": str(crop_path),
                "ocr_text": ocr_text,
            },
        }
        return [
            json.dumps(result, ensure_ascii=False, indent=2),
            Image(path=str(crop_path)),
        ]
    except asyncio.TimeoutError:
        return [f"Error: Crop extraction timed out after {NETWORK_TIMEOUT} seconds."]
    except Exception as exc:
        return [f"Error during crop extraction: {exc}"]


def _parse_duration_str(duration_str: str) -> int:
    """Parse duration string like '14m 32s' or '1h 5m 32s' to seconds."""
    total = 0
    hour_match = re.search(r'(\d+)h', duration_str)
    min_match = re.search(r'(\d+)m', duration_str)
    sec_match = re.search(r'(\d+)s', duration_str)
    if hour_match:
        total += int(hour_match.group(1)) * 3600
    if min_match:
        total += int(min_match.group(1)) * 60
    if sec_match:
        total += int(sec_match.group(1))
    if total == 0:
        log.warning("Could not parse duration string: '%s'", duration_str)
    return total


def _build_transcript_text(cached_data: dict = None, transcript_text: str = None, metadata: dict = None, url: str = "", prefix: str = "") -> tuple[str, str, dict]:
    """Build the transcript section from cached data or fresh fetch."""
    if cached_data:
        meta = cached_data.get("metadata", {})
        transcript = cached_data.get("transcript", "")
    else:
        meta = metadata or {}
        transcript = transcript_text or ""

    chapters_list = meta.get("chapters", [])
    chapters_section = "\n".join(chapters_list) if chapters_list else "None available"

    header = (
        (f"{prefix}\n" if prefix else "") +
        f"Title: {meta.get('title', 'Unknown')}\n"
        f"Creator: {meta.get('uploader', 'Unknown')}\n"
        f"Duration: {meta.get('duration', 'Unknown')}\n"
        f"Views: {(meta.get('views') or 0):,}\n"
        f"URL: {url}\n"
        f"CHAPTER STRUCTURE:\n{chapters_section}\n"
        f"==================================================\n\n"
    )
    return header, transcript, meta


@mcp.tool()
async def inspect_ocular_audio_source(source: str) -> str:
    """Resolve a URL or local media file without downloading or analyzing it."""
    cookies_path = find_cookies_file()
    try:
        resolved = await asyncio.wait_for(
            asyncio.to_thread(resolve_media_source, source, cookies_path),
            timeout=NETWORK_TIMEOUT,
        )
    except asyncio.TimeoutError:
        return "[ERROR] Media source resolution timed out."
    except Exception as exc:
        return f"[ERROR] Invalid media source: {exc}"

    safe = dict(resolved)
    safe.pop("source", None)
    return json.dumps(safe, ensure_ascii=False, indent=2)


@mcp.tool()
async def get_ocular_audio_capabilities() -> str:
    """
    Returns system capabilities and dependency status.

    Use this tool to check what features are available before making other requests.
    Returns information about Python, FFmpeg, Whisper, Tesseract, OpenCV, and cookie status.
    """
    log.info("Checking system capabilities...")
    caps = _check_system_capabilities()

    output = [
        "[SYSTEM CAPABILITIES]",
        f"OcularAudio: {caps['ocular_audio_version']}",
        f"Python: {caps['python_version']}",
        f"Analysis Levels: {', '.join(caps['supported_analysis_levels'])}",
        f"Source Types: {', '.join(caps['supported_source_types'])}",
        f"FFmpeg: {'Available' if caps['ffmpeg'] else 'NOT FOUND - Required for video processing'}",
        f"OpenCV: {'Available' if caps['opencv'] else 'NOT FOUND - Required for screenshots'}",
        f"Whisper: {'Available (' + caps['whisper']['engine'] + ', model: ' + caps['whisper']['model_size'] + ')' if caps['whisper']['available'] else 'NOT FOUND - Optional for local transcription'}",
        f"Tesseract OCR: {'Available at ' + caps['tesseract']['path'] if caps['tesseract']['available'] else 'NOT FOUND - Optional for text extraction (--ocr flag)'}",
        f"Cookies File: {'Found' if caps['cookies_found'] else 'Not found (optional, needed for age-restricted videos)'}",
        f"Cache Directory: {caps['cache_dir']}",
        f"Visual Evidence: {'Available' if caps['visual_evidence']['available'] else 'Unavailable'}",
        f"Visual Cache: {caps['visual_evidence']['cache_dir']}",
    ]

    return "\n".join(output)


@mcp.tool()
async def get_ocular_audio_metadata(url: str) -> str:
    """
    Extracts only video metadata (title, creator, duration, views, chapters) without transcript.

    Use this when you need quick video info without the full transcript.
    Much faster than get_ocular_audio_transcript if you only need metadata.
    """
    log.info("Fetching metadata for: %s", url)
    video_id = extract_video_id(url)
    is_youtube = bool(video_id)
    cache_id = _cache_id(url)
    cookies_path = find_cookies_file()

    # Check cache first
    cached_data = read_from_cache(cache_id)
    if cached_data:
        log.info("Cache hit for metadata: %s", cache_id)
        meta = cached_data.get("metadata", {})
    else:
        try:
            metadata = await asyncio.wait_for(
                asyncio.to_thread(_blocking_metadata_fetch, url, cookies_path),
                timeout=NETWORK_TIMEOUT
            )
            meta = metadata
        except asyncio.TimeoutError:
            log.error("Metadata fetch timed out after %ds", NETWORK_TIMEOUT)
            return "[ERROR] Metadata fetch timed out. Check your network connection."
        except Exception as e:
            log.warning("Metadata fetch failed: %s", e)
            return f"[ERROR] Failed to fetch metadata: {str(e)}"

    chapters = meta.get("chapters", [])
    chapters_section = "\n".join(chapters) if chapters else "None available"

    output = [
        "[VIDEO METADATA]",
        f"Title: {meta.get('title', 'Unknown')}",
        f"Creator: {meta.get('uploader', 'Unknown')}",
        f"Duration: {meta.get('duration', 'Unknown')}",
        f"Views: {(meta.get('views') or 0):,}",
        f"Upload Date: {meta.get('upload_date', 'N/A')}",
        f"URL: {url}",
        f"Source: {meta.get('source', {}).get('source_kind', 'unknown')}",
        f"Platform: {meta.get('source', {}).get('platform', 'unknown')}",
        f"Live: {meta.get('source', {}).get('is_live', False)}",
        f"Capabilities: {', '.join(k for k, v in meta.get('source', {}).get('capabilities', {}).items() if v)}",
        "",
        "CHAPTERS:",
        chapters_section,
    ]

    return "\n".join(output)


@mcp.tool()
async def get_ocular_audio_chapters(url: str) -> str:
    """
    Extracts only video chapters with timestamps.

    Use this when you need to understand the video structure without getting the full transcript.
    Returns chapter titles with start times in [MM:SS] format.
    """
    log.info("Fetching chapters for: %s", url)
    video_id = extract_video_id(url)
    is_youtube = bool(video_id)
    cache_id = _cache_id(url)
    cookies_path = find_cookies_file()

    # Check cache first
    cached_data = read_from_cache(cache_id)
    if cached_data:
        meta = cached_data.get("metadata", {})
    else:
        try:
            meta = await asyncio.wait_for(
                asyncio.to_thread(_blocking_metadata_fetch, url, cookies_path),
                timeout=NETWORK_TIMEOUT
            )
        except asyncio.TimeoutError:
            return "[ERROR] Metadata fetch timed out."
        except Exception as e:
            return f"[ERROR] Failed to fetch chapters: {str(e)}"

    chapters = meta.get("chapters", [])
    if not chapters:
        output = [
            "[VIDEO CHAPTERS]",
            f"Title: {meta.get('title', 'Unknown')}",
            f"URL: {url}",
            "",
            "No chapters available for this video.",
        ]
    else:
        output = [
            "[VIDEO CHAPTERS]",
            f"Title: {meta.get('title', 'Unknown')}",
            f"URL: {url}",
            f"Total Chapters: {len(chapters)}",
            "",
            "CHAPTERS:",
            "\n".join(chapters),
        ]

    return "\n".join(output)


@mcp.tool()
async def list_ocular_audio_cache() -> str:
    """
    Lists all cached videos with their metadata.

    Shows video titles, uploaders, duration, and when they were cached.
    Use this to see what videos have been previously processed.
    """
    log.info("Listing cached videos...")
    videos = _get_cache_list()

    if not videos:
        return "[CACHE] No cached videos found.\nCache directory: " + str(CACHE_DIR)

    output = [f"[CACHE] {len(videos)} cached video(s):", ""]
    for i, v in enumerate(videos, 1):
        cached_time = time.strftime("%Y-%m-%d %H:%M", time.localtime(v["cached_at"])) if v["cached_at"] else "unknown"
        output.append(f"{i}. {v['title']}")
        output.append(f"   Creator: {v['uploader']}")
        output.append(f"   Duration: {v['duration']}")
        output.append(f"   Method: {v['method']}")
        output.append(f"   Cached: {cached_time}")
        output.append(f"   ID: {v['id']}")
        output.append("")

    return "\n".join(output)


@mcp.tool()
async def clear_ocular_audio_cache(video_id: str = "") -> str:
    """
    Clears cached video data.

    Args:
        video_id: Optional video ID to clear specific video. If empty, clears all cache.
    """
    if video_id:
        log.info("Clearing cache for video: %s", video_id)
        result = _clear_cache(video_id)
        if result["cleared"] > 0:
            return f"[CACHE] Cleared cache for video: {video_id}"
        else:
            return f"[CACHE] Video {video_id} not found in cache."
    else:
        log.info("Clearing all cache...")
        result = _clear_cache()
        return f"[CACHE] {result['message']}"


@mcp.tool()
async def get_ocular_audio_video_context(
    url: str,
    detail_level: str = "auto",
    use_local_whisper: bool = True,
    enable_ocr: bool = False,
    analysis_depth: str = "understand"
) -> list:
    """
    Extracts transcript, metadata, and optional intelligent screenshots from a video.

    Automatically analyzes the transcript to find visually important moments
    and captures screenshots at those timestamps. Returns everything combined.

    Modes:
      - "auto" (default): Adapts screenshot count to video length and content importance.
      - "overview": Transcript and metadata only, no screenshots. Fastest.
      - "balanced": Captures screenshots only at visually important moments (strong signals).
      - "deep": Captures screenshots at every visually significant moment (all signals).

    Args:
        url: The full YouTube or Web video URL.
        detail_level: Control how much visual content to extract ("auto", "overview", "balanced", "deep").
        use_local_whisper: Enable offline local transcribing fallback.
        enable_ocr: If True, run OCR on captured screenshots to extract visible text.
    """
    valid_modes = ("auto", "overview", "balanced", "deep")
    if detail_level not in valid_modes:
        log.warning("Invalid detail_level '%s', falling back to 'auto'.", detail_level)
        detail_level = "auto"

    try:
        normalized_depth = normalize_analysis_level(analysis_depth)
    except ValueError as exc:
        return [f"Error: {exc}"]

    if normalized_depth == "glance":
        detail_level = "overview"
    elif normalized_depth == "deep":
        detail_level = "deep"
    elif normalized_depth == "omniscient":
        detail_level = "deep"
        enable_ocr = True

    video_id = extract_video_id(url)
    is_youtube = bool(video_id)
    cache_id = _cache_id(url)
    cookies_path = find_cookies_file()

    # 1. CHECK CACHE
    cached_data = read_from_cache(cache_id)
    transcript_text = ""
    metadata = {}

    if cached_data:
        log.info("Cache hit for %s.", cache_id)
        header, transcript_text, metadata = _build_transcript_text(cached_data=cached_data, url=url)
    else:
        # 2. FETCH METADATA
        log.info("Fetching video metadata...")
        try:
            metadata = await asyncio.wait_for(
                asyncio.to_thread(_blocking_metadata_fetch, url, cookies_path),
                timeout=NETWORK_TIMEOUT
            )
        except asyncio.TimeoutError:
            log.error("Metadata fetch timed out after %ds", NETWORK_TIMEOUT)
            metadata = _default_metadata(cache_id)
        except Exception as e:
            log.warning("Metadata fetch failed: %s", e)
            metadata = _default_metadata(cache_id)

        # 3. FETCH TRANSCRIPT
        if is_youtube:
            try:
                log.info("Querying YouTube captions...")
                session = get_authenticated_session(cookies_path)

                def fetch_captions():
                    api = YouTubeTranscriptApi(http_client=session)
                    return api.fetch(video_id)

                transcript_list = await asyncio.wait_for(
                    asyncio.to_thread(fetch_captions),
                    timeout=NETWORK_TIMEOUT
                )
                formatted_segments = []
                for entry in transcript_list:
                    timestamp = format_seconds(entry.start)
                    formatted_segments.append(f"{timestamp} {entry.text}")
                transcript_text = "\n".join(formatted_segments)

                write_to_cache(cache_id, {
                    "metadata": metadata,
                    "transcript": transcript_text,
                    "method": "official_captions",
                    "timestamp": time.time()
                })
            except (asyncio.TimeoutError, Exception) as e:
                if isinstance(e, asyncio.TimeoutError):
                    log.error("Caption fetch timed out after %ds, trying Whisper...", NETWORK_TIMEOUT)
                else:
                    log.info("Caption API failed: %s, trying Whisper...", e)
                if use_local_whisper:
                    try:
                        target_param = video_id if is_youtube else url
                        transcript_text = await asyncio.wait_for(
                            asyncio.to_thread(_blocking_whisper_transcription, target_param, cookies_path),
                            timeout=NETWORK_TIMEOUT
                        )
                        write_to_cache(cache_id, {
                            "metadata": metadata,
                            "transcript": transcript_text,
                            "method": "local_whisper_fallback",
                            "timestamp": time.time()
                        })
                    except Exception as we:
                        log.error("Whisper fallback failed: %s", we)
                        return [f"Error: Transcript extraction failed. Details: {str(we)}"]
                else:
                    return ["Error: No captions available and Whisper fallback is disabled."]
        elif use_local_whisper:
            try:
                transcript_text = await asyncio.wait_for(
                    asyncio.to_thread(_blocking_whisper_transcription, url, cookies_path),
                    timeout=NETWORK_TIMEOUT
                )
                write_to_cache(cache_id, {
                    "metadata": metadata,
                    "transcript": transcript_text,
                    "method": "local_whisper_fallback",
                    "timestamp": time.time()
                })
            except Exception as we:
                log.error("Whisper transcription failed: %s", we)
                return [f"Error: Transcript extraction failed. Details: {str(we)}"]
        else:
            return ["Error: No captions available and Whisper fallback is disabled."]

        header, _, _ = _build_transcript_text(
            transcript_text=transcript_text, metadata=metadata, url=url
        )

    # 4. OVERVIEW MODE — no screenshots
    if detail_level == "overview":
        return [
            "[VIDEO CONTEXT - OVERVIEW]",
            header,
            "[TRANSCRIPT]",
            transcript_text
        ]

    # 5. CALCULATE SCREENSHOT TIMESTAMPS
    duration_secs = _parse_duration_str(metadata.get("duration", "0"))
    if duration_secs == 0:
        lines = transcript_text.strip().split('\n')
        for line in reversed(lines):
            match = re.match(r'\[(\d+):(\d+)\]', line)
            if match:
                duration_secs = int(match.group(1)) * 60 + int(match.group(2))
                break

    key_moments = extract_key_timestamps(transcript_text, duration_secs, mode=detail_level)

    if not key_moments:
        return [
            "[VIDEO CONTEXT - NO VISUAL KEYPOINTS FOUND]",
            header,
            "[TRANSCRIPT]",
            transcript_text
        ]

    # 6. CAPTURE SCREENSHOTS
    timestamps_secs = [m[0] for m in key_moments]
    log.info("Capturing %d screenshots at: %s", len(timestamps_secs), timestamps_secs)

    screenshot_payload = []
    try:
        screenshot_payload = await asyncio.wait_for(
            asyncio.to_thread(_blocking_screenshot_extractor, url, timestamps_secs, cookies_path, enable_ocr),
            timeout=NETWORK_TIMEOUT
        )
    except asyncio.TimeoutError:
        log.error("Screenshot extraction timed out after %ds", NETWORK_TIMEOUT)
        screenshot_payload = [f"Error: Screenshot extraction timed out after {NETWORK_TIMEOUT} seconds."]
    except Exception as e:
        log.error("Screenshot extraction failed: %s", e)
        screenshot_payload = [f"Error during screenshot extraction: {str(e)}"]

    # 7. BUILD FINAL OUTPUT
    keypoints_section = "\n".join(
        f"  {format_seconds(ts)} — {reason} (score: {score})"
        for ts, reason, score in key_moments
    )

    success_count = sum(1 for item in screenshot_payload if hasattr(item, 'path'))
    result = [
        f"[VIDEO CONTEXT - TRANSCRIPT + VISUALS]",
        f"Detail Level: {detail_level} | Analysis Depth: {normalized_depth} ({success_count} screenshots captured)",
        header,
        "[VISUAL KEYPOINTS]",
        keypoints_section,
        "",
        "[TRANSCRIPT]",
        transcript_text,
        "",
        "[SCREENSHOTS]",
    ]

    for item in screenshot_payload:
        if isinstance(item, str) and (item.startswith("[WARNING") or item.startswith("Error")):
            result.append(item)
        elif hasattr(item, 'path'):
            result.append(item)

    return result



async def _ensure_evidence_cache(url: str, use_local_whisper: bool = True) -> tuple[str, dict]:
    """Return cached transcript evidence, populating the cache when necessary."""
    cache_id = _cache_id(url)
    cached = read_from_cache(cache_id)
    if cached:
        return cache_id, cached
    await get_ocular_audio_transcript(url, use_local_whisper=use_local_whisper)
    cached = read_from_cache(cache_id)
    if not cached:
        raise RuntimeError("Transcript evidence is unavailable; run transcription successfully first.")
    return cache_id, cached


def _evidence_payload(segment) -> dict:
    return {
        "evidence_id": segment.evidence_id,
        "timestamp": format_timestamp(segment.start_seconds),
        "start_seconds": segment.start_seconds,
        "end_seconds": segment.end_seconds,
        "score": segment.score,
        "chapter": segment.chapter,
        "text": segment.text,
        "source": segment.source,
    }


@mcp.tool()
async def search_ocular_audio_video(
    url: str,
    query: str,
    top_k: int = 8,
    min_score: float = 0.0,
    use_local_whisper: bool = True,
) -> str:
    """Search a video's timestamped transcript evidence and return ranked moments."""
    if not query or not query.strip():
        return json.dumps({"error": "query must not be empty"}, ensure_ascii=False)
    try:
        cache_id, cached = await _ensure_evidence_cache(url, use_local_whisper)
        metadata = cached.get("metadata", {})
        source = metadata.get("source", {})
        duration = _parse_duration_str(metadata.get("duration", "0"))
        if not duration:
            duration = float(source.get("duration_seconds") or 0)
        segments = build_evidence_segments(
            cached.get("transcript", ""),
            duration_seconds=duration,
            chapters=metadata.get("chapters", []),
        )
        results = search_evidence(segments, query, top_k=top_k, min_score=min_score)
        payload = {
            "source_id": cache_id,
            "url": url,
            "title": metadata.get("title", "Unknown"),
            "query": query.strip(),
            "result_count": len(results),
            "results": [
                {
                    **_evidence_payload(item),
                    "suggested_window": {
                        "start_seconds": max(0, item.start_seconds - 5),
                        "end_seconds": item.end_seconds + 5,
                    },
                }
                for item in results
            ],
        }
        return json.dumps(payload, ensure_ascii=False, indent=2)
    except Exception as exc:
        log.warning("Evidence search failed: %s", exc)
        return json.dumps({"error": str(exc)}, ensure_ascii=False)


@mcp.tool()
async def get_ocular_audio_video_timeline(
    url: str,
    start_seconds: float = 0,
    end_seconds: float = -1,
    use_local_whisper: bool = True,
) -> str:
    """Return timestamped transcript evidence for a bounded section of a video."""
    try:
        cache_id, cached = await _ensure_evidence_cache(url, use_local_whisper)
        metadata = cached.get("metadata", {})
        duration = _parse_duration_str(metadata.get("duration", "0"))
        segments = build_evidence_segments(
            cached.get("transcript", ""),
            duration_seconds=duration,
            chapters=metadata.get("chapters", []),
        )
        end = None if end_seconds < 0 else max(start_seconds, end_seconds)
        selected = timeline_window(segments, start_seconds, end)
        return json.dumps({
            "source_id": cache_id,
            "url": url,
            "title": metadata.get("title", "Unknown"),
            "start_seconds": max(0, start_seconds),
            "end_seconds": end,
            "segments": [_evidence_payload(item) for item in selected],
        }, ensure_ascii=False, indent=2)
    except Exception as exc:
        return json.dumps({"error": str(exc)}, ensure_ascii=False)


@mcp.tool()
async def inspect_ocular_audio_moment(
    url: str,
    timestamp_seconds: float,
    window_seconds: float = 15,
    enable_ocr: bool = False,
    use_local_whisper: bool = True,
) -> list:
    """Inspect one moment with the nearest transcript evidence and a targeted frame."""
    if timestamp_seconds < 0:
        return ["Error: timestamp_seconds must be >= 0."]
    try:
        cache_id, cached = await _ensure_evidence_cache(url, use_local_whisper)
        metadata = cached.get("metadata", {})
        duration = _parse_duration_str(metadata.get("duration", "0"))
        segments = build_evidence_segments(
            cached.get("transcript", ""),
            duration_seconds=duration,
            chapters=metadata.get("chapters", []),
        )
        nearest = nearest_evidence(segments, timestamp_seconds)
        start = max(0, timestamp_seconds - max(0, window_seconds))
        end = timestamp_seconds + max(0, window_seconds)
        nearby = timeline_window(segments, start, end)
        frame_payload = await asyncio.wait_for(
            asyncio.to_thread(
                _blocking_screenshot_extractor,
                url,
                [int(timestamp_seconds)],
                find_cookies_file(),
                enable_ocr,
            ),
            timeout=NETWORK_TIMEOUT,
        )
        result = [
            json.dumps({
                "source_id": cache_id,
                "url": url,
                "timestamp_seconds": timestamp_seconds,
                "timestamp": format_timestamp(timestamp_seconds),
                "nearest_evidence": _evidence_payload(nearest) if nearest else None,
                "nearby_evidence": [_evidence_payload(item) for item in nearby],
            }, ensure_ascii=False, indent=2)
        ]
        result.extend(frame_payload)
        return result
    except asyncio.TimeoutError:
        return [f"Error: Moment inspection timed out after {NETWORK_TIMEOUT} seconds."]
    except Exception as exc:
        return [f"Error during moment inspection: {exc}"]


@mcp.tool()
async def search_ocular_audio_cache(query: str, top_k: int = 10) -> str:
    """Search all locally cached transcripts and return ranked timestamped evidence."""
    if not query or not query.strip():
        return json.dumps({"error": "query must not be empty"}, ensure_ascii=False)
    matches = []
    for cache_file in CACHE_DIR.glob("*.json"):
        cached = read_from_cache(cache_file.stem)
        if not cached:
            continue
        metadata = cached.get("metadata", {})
        duration = _parse_duration_str(metadata.get("duration", "0"))
        segments = build_evidence_segments(
            cached.get("transcript", ""),
            duration_seconds=duration,
            chapters=metadata.get("chapters", []),
        )
        for item in search_evidence(segments, query, top_k=min(top_k, 10)):
            title = metadata.get("title", "Unknown")
            matches.append({
                **_evidence_payload(item),
                "source_id": cache_file.stem,
                "title": title,
                "uploader": metadata.get("uploader", ""),
            })
    matches.sort(key=lambda item: (-item["score"], item["source_id"], item["start_seconds"]))
    return json.dumps({
        "query": query.strip(),
        "result_count": min(len(matches), max(1, min(int(top_k), 50))),
        "results": matches[:max(1, min(int(top_k), 50))],
    }, ensure_ascii=False, indent=2)


def copy_to_clipboard_native(text: str) -> bool:
    try:
        if sys.platform == 'darwin':
            subprocess.run(['pbcopy'], input=text, text=True, check=True)
            return True
        elif sys.platform == 'win32':
            subprocess.run(['clip'], input=text, text=True, check=True)
            return True
        else:
            try:
                subprocess.run(['xclip', '-selection', 'clipboard'], input=text, text=True, check=True)
                return True
            except (FileNotFoundError, subprocess.CalledProcessError):
                try:
                    subprocess.run(['xsel', '--clipboard', '--input'], input=text, text=True, check=True)
                    return True
                except (FileNotFoundError, subprocess.CalledProcessError):
                    pass
    except Exception:
        pass
    return False


if __name__ == "__main__":
    # Handle --check mode (no URL required)
    if "--check" in sys.argv:
        caps = _check_system_capabilities()
        print("[SYSTEM CAPABILITIES]")
        print(f"Python: {caps['python_version']}")
        print(f"FFmpeg: {'OK' if caps['ffmpeg'] else 'MISSING'}")
        print(f"OpenCV: {'OK' if caps['opencv'] else 'MISSING'}")
        if caps['whisper']['available']:
            print(f"Whisper: OK ({caps['whisper']['engine']}, model: {caps['whisper']['model_size']})")
        else:
            print("Whisper: MISSING (optional)")
        if caps['tesseract']['available']:
            print(f"Tesseract OCR: OK ({caps['tesseract']['path']})")
        else:
            print("Tesseract OCR: MISSING (optional)")
        print(f"Cookies: {'Found' if caps['cookies_found'] else 'Not found'}")
        print(f"Cache: {caps['cache_dir']}")
        sys.exit(0)

    if len(sys.argv) > 1 and not sys.argv[1].startswith("-"):
        target_url = sys.argv[1]
        detail_level = sys.argv[2] if len(sys.argv) > 2 else "auto"

        # Parse output control flags
        no_clipboard = "--no-clipboard" in sys.argv
        json_output = "--json" in sys.argv
        stdout_mode = "--stdout" in sys.argv
        enable_ocr = "--ocr" in sys.argv
        visual_index_mode = "--visual-index" in sys.argv
        visual_search_query = None
        frame_at = None
        frame_burst = None
        if "--visual-search" in sys.argv:
            idx = sys.argv.index("--visual-search")
            if idx + 1 < len(sys.argv):
                visual_search_query = sys.argv[idx + 1]
        if "--frame-at" in sys.argv:
            idx = sys.argv.index("--frame-at")
            if idx + 1 < len(sys.argv):
                frame_at = float(sys.argv[idx + 1])
        if "--frame-burst" in sys.argv:
            idx = sys.argv.index("--frame-burst")
            if idx + 3 < len(sys.argv):
                frame_burst = (
                    float(sys.argv[idx + 1]),
                    float(sys.argv[idx + 2]),
                    int(sys.argv[idx + 3]),
                )
        analysis_depth = "understand"
        if "--analysis-depth" in sys.argv:
            idx = sys.argv.index("--analysis-depth")
            if idx + 1 < len(sys.argv):
                analysis_depth = sys.argv[idx + 1]
        force_mode = "--force" in sys.argv
        verbose_mode = "--verbose" in sys.argv
        quiet_mode = "--quiet" in sys.argv
        output_file = None
        for i, arg in enumerate(sys.argv):
            if arg == "--output" and i + 1 < len(sys.argv):
                output_file = sys.argv[i + 1]

        # Set logging level based on verbosity
        if quiet_mode:
            logging.getLogger().setLevel(logging.WARNING)
        elif verbose_mode:
            logging.getLogger().setLevel(logging.DEBUG)

        async def run_standalone():
            start_time = time.time()
            log.info("Processing target resource: %s (detail: %s)", target_url, detail_level)

            # ── Phase 3 visual commands ───────────────────────────────────
            if visual_index_mode:
                print(await index_ocular_audio_video_visuals(
                    url=target_url,
                    enable_ocr=enable_ocr,
                    force=force_mode,
                ))
                return

            if visual_search_query is not None:
                print(await search_ocular_audio_visuals(
                    url=target_url,
                    query=visual_search_query,
                ))
                return

            if frame_at is not None:
                result = await get_ocular_audio_video_frame(
                    url=target_url,
                    timestamp_seconds=frame_at,
                    enable_ocr=enable_ocr,
                )
                for item in result:
                    print(item.path if hasattr(item, "path") else item)
                return

            if frame_burst is not None:
                center, radius, count = frame_burst
                result = await get_ocular_audio_video_frame_burst(
                    url=target_url,
                    center_seconds=center,
                    radius_seconds=radius,
                    count=count,
                    enable_ocr=enable_ocr,
                )
                for item in result:
                    print(item.path if hasattr(item, "path") else item)
                return

            # ── JSON mode: call underlying functions for structured data ─────
            if json_output:
                import json as _json
                video_id = extract_video_id(target_url)
                is_youtube = bool(video_id)
                cookies_path = find_cookies_file()
                cached = read_from_cache(video_id) if video_id and not force_mode else None
                if cached:
                    meta = cached.get("metadata", {})
                    transcript = cached.get("transcript", "")
                else:
                    meta = await asyncio.to_thread(_blocking_metadata_fetch, target_url, cookies_path)
                    transcript_text = None
                    if is_youtube:
                        try:
                            session = get_authenticated_session(cookies_path)
                            def fetch_captions():
                                api = YouTubeTranscriptApi(http_client=session)
                                return api.fetch(video_id)
                            transcript_list = await asyncio.wait_for(
                                asyncio.to_thread(fetch_captions),
                                timeout=NETWORK_TIMEOUT
                            )
                            formatted_segments = []
                            for entry in transcript_list:
                                timestamp = format_seconds(entry.start)
                                formatted_segments.append(f"{timestamp} {entry.text}")
                            transcript_text = "\n".join(formatted_segments)
                        except Exception:
                            transcript_text = None
                    if not transcript_text:
                        try:
                            target_param = video_id if is_youtube else target_url
                            transcript_text = await asyncio.wait_for(
                                asyncio.to_thread(_blocking_whisper_transcription, target_param, cookies_path),
                                timeout=NETWORK_TIMEOUT
                            )
                        except Exception:
                            transcript_text = "(transcription unavailable)"
                    transcript = transcript_text or ""
                    if video_id:
                        write_to_cache(video_id, {
                            "metadata": meta,
                            "transcript": transcript,
                            "method": "official_captions" if transcript_text and transcript_text != "(transcription unavailable)" else "local_whisper_fallback",
                            "timestamp": time.time(),
                        })

                json_data = {
                    "video_id": video_id,
                    "url": target_url,
                    "metadata": {
                        "title": meta.get("title", "Unknown"),
                        "uploader": meta.get("uploader", "Unknown"),
                        "duration": meta.get("duration", "Unknown"),
                        "views": meta.get("views", 0),
                        "upload_date": meta.get("upload_date", ""),
                        "chapters": meta.get("chapters", []),
                    },
                    "transcript": transcript,
                }
                print(_json.dumps(json_data, indent=2))
                return

            # ── Normal mode: call the all-in-one context tool ────────────────
            res = await get_ocular_audio_video_context(
                url=target_url,
                detail_level=detail_level,
                use_local_whisper=True,
                enable_ocr=enable_ocr,
                analysis_depth=analysis_depth
            )

            output_lines = []
            for item in res:
                if hasattr(item, 'path'):
                    output_lines.append(f"[Screenshot saved: {item.path}]")
                else:
                    output_lines.append(str(item))

            prompt_context = "\n".join(output_lines)

            # Sanitize output to remove non-ASCII characters that may cause encoding errors
            prompt_context = prompt_context.encode('ascii', errors='ignore').decode('ascii')

            # Print transcript to stdout (always, so CLI wrapper can capture it)
            try:
                print(prompt_context)
            except UnicodeEncodeError:
                # Fallback: encode with replacement
                print(prompt_context.encode('ascii', errors='replace').decode('ascii'))

            # ── Output control ──────────────────────────────────────────────
            if stdout_mode:
                # stdout-only mode, no clipboard or file write
                pass
            elif output_file:
                # Write to specific file
                with open(output_file, "w", encoding="utf-8") as f:
                    f.write(prompt_context)
                print("\n" + "=" * 60, file=sys.stderr)
                print(f"[SUCCESS: Saved to {output_file}]", file=sys.stderr)
                print("=" * 60, file=sys.stderr)
            elif not no_clipboard:
                # Default: try clipboard, fallback to file
                success = copy_to_clipboard_native(prompt_context)
                if success:
                    print("\n" + "=" * 60, file=sys.stderr)
                    print("[SUCCESS: Context Copied to Clipboard]", file=sys.stderr)
                    print("[INSTRUCTION: Paste into Claude Web/ChatGPT]", file=sys.stderr)
                    print("=" * 60, file=sys.stderr)
                else:
                    fallback_path = os.path.join(os.getcwd(), "video_context.txt")
                    with open(fallback_path, "w", encoding="utf-8") as f:
                        f.write(prompt_context)
                    print("\n" + "=" * 60, file=sys.stderr)
                    print("[SUCCESS: Transcribed Successfully]", file=sys.stderr)
                    print(f"[INFO: Saved to {fallback_path}]", file=sys.stderr)
                    print("=" * 60, file=sys.stderr)

            # Print summary line
            elapsed = time.time() - start_time
            screenshot_count = sum(1 for item in res if hasattr(item, 'path'))
            ocr_count = sum(1 for item in res if isinstance(item, str) and item.startswith("[OCR"))
            if not quiet_mode:
                print(f"\n[SUMMARY] Processed in {elapsed:.1f}s | {screenshot_count} screenshots | {ocr_count} OCR results", file=sys.stderr)

        try:
            asyncio.run(run_standalone())
        except KeyboardInterrupt:
            print("\n[INFO] Interrupted by user.", file=sys.stderr)
            sys.exit(130)
        except UnicodeEncodeError:
            # Handle encoding errors at the top level
            print("[ERROR] Output contains characters that cannot be encoded. Try --stdout flag.", file=sys.stderr)
            sys.exit(1)
        except Exception as e:
            print(f"\n[ERROR] {type(e).__name__}: {e}", file=sys.stderr)
            sys.exit(1)
    else:
        mcp.run()
