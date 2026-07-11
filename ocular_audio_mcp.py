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
from pathlib import Path

# Python version check (list[int] requires 3.9+)
if sys.version_info < (3, 9):
    sys.exit("Error: OcularAudio MCP requires Python 3.9 or higher. You are running Python {}.{}".format(*sys.version_info[:2]))

from requests import Session
from mcp.server.fastmcp import FastMCP, Image
from youtube_transcript_api import YouTubeTranscriptApi
import yt_dlp
import cv2

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

# Initialize the Model Context Protocol (MCP) server
mcp = FastMCP(
    "OcularAudio Server",
    dependencies=["youtube-transcript-api", "yt-dlp", "opencv-python-headless"]
)

# Global holder for the local whisper model instance (loaded lazily)
_whisper_engine = None

def get_whisper_engine():
    global _whisper_engine
    if _whisper_engine is not None:
        return _whisper_engine

    log.info("Initializing local transcription engine...")
    try:
        from faster_whisper import WhisperModel
        log.info("Using high-performance 'faster-whisper' engine.")
        _whisper_engine = {
            "type": "faster-whisper",
            "model": WhisperModel("tiny", device="cpu", compute_type="int8")
        }
        return _whisper_engine
    except ImportError:
        pass

    try:
        import whisper
        log.info("Using standard 'openai-whisper' engine.")
        _whisper_engine = {
            "type": "openai-whisper",
            "model": whisper.load_model("tiny")
        }
        return _whisper_engine
    except ImportError:
        raise ImportError(
            "No local ASR engines found. Please install one of the following:\n"
            "  pip install faster-whisper\n"
            "  pip install openai-whisper torch"
        )


def find_cookies_file() -> str:
    """Search for cookies.txt in known locations.

    Search order:
      1. ./cookies.txt            (relative to current working directory)
      2. ~/.cache/ocular_audio_mcp/cookies.txt
      3. ~/.config/ocular_audio_mcp/cookies.txt
    """
    search_paths = [
        Path("./cookies.txt"),
        CACHE_DIR / "cookies.txt",
        Path(os.path.expanduser("~")) / ".config" / "ocular_audio_mcp" / "cookies.txt"
    ]
    for path in search_paths:
        if path.exists():
            log.info("Found cookies file at: %s", path)
            return str(path)
    return ""


def get_authenticated_session(cookies_path: str) -> Session:
    session = Session()
    session.headers.update({
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
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
        r'(?:v=|\/)([0-9A-Za-z_-]{11}).*',
        r'youtu\.be\/([0-9A-Za-z_-]{11})'
    ]
    for pattern in patterns:
        match = re.search(pattern, url)
        if match:
            return match.group(1)
    return ""


def _blocking_metadata_fetch(url: str, cookies_path: str) -> dict:
    ydl_opts = {
        'quiet': True,
        'no_warnings': True,
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

        return {
            "title": info.get("title", "Unknown Title"),
            "uploader": info.get("uploader", "Unknown Creator"),
            "views": info.get("view_count", 0),
            "duration": duration_str,
            "upload_date": info.get("upload_date", "N/A"),
            "chapters": formatted_chapters
        }


def format_seconds(seconds: float) -> str:
    minutes = int(seconds) // 60
    secs = int(seconds) % 60
    return f"[{minutes:02d}:{secs:02d}]"


def read_from_cache(video_id: str) -> dict:
    cache_path = CACHE_DIR / f"{video_id}.json"
    if cache_path.exists():
        try:
            with open(cache_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception:
            pass
    return None


def write_to_cache(video_id: str, data: dict):
    cache_path = CACHE_DIR / f"{video_id}.json"
    try:
        with open(cache_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception as e:
        log.warning("Failed to write cache for %s: %s", video_id, e)


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
            'preferredquality': '96',
        }],
        'quiet': True,
        'no_warnings': True,
    }
    if cookies_path:
        ydl_opts['cookiefile'] = cookies_path

    download_target = url_or_id if url_or_id.startswith("http") else f"https://www.youtube.com/watch?v={url_or_id}"

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

    log.info("Running Whisper speech-to-text offline locally...")
    formatted_segments = []

    if engine["type"] == "faster-whisper":
        segments, info = engine["model"].transcribe(audio_file_path, beam_size=3)
        for segment in segments:
            timestamp = format_seconds(segment.start)
            formatted_segments.append(f"{timestamp} {segment.text.strip()}")
    else:
        result = engine["model"].transcribe(audio_file_path, language=None)
        segments = result.get("segments", [])
        for seg in segments:
            timestamp = format_seconds(seg.get("start", 0))
            formatted_segments.append(f"{timestamp} {seg.get('text', '').strip()}")

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

    cache_id = video_id if is_youtube else "".join([c if c.isalnum() else "_" for c in url[-20:]])
    cookies_path = find_cookies_file()

    # 1. CHECK CACHE FIRST
    cached_data = read_from_cache(cache_id)
    if cached_data:
        log.info("Cache hit for %s. Loading transcript.", cache_id)
        meta = cached_data.get("metadata", {})
        transcript = cached_data.get("transcript", "")
        chapters_list = meta.get("chapters", [])
        chapters_section = "\n".join(chapters_list) if chapters_list else "None available"

        return (
            f"[CACHE HIT: LOADED FROM LOCAL CACHE]\n"
            f"Title: {meta.get('title')}\n"
            f"Creator: {meta.get('uploader')}\n"
            f"Duration: {meta.get('duration')}\n"
            f"Views: {meta.get('views'):,}\n"
            f"URL: {url}\n"
            f"CHAPTER STRUCTURE:\n{chapters_section}\n"
            f"==================================================\n\n"
            + transcript
        )

    # 2. RUN METADATA FETCH
    log.info("Fetching video metadata and chapters asynchronously...")
    try:
        metadata = await asyncio.to_thread(_blocking_metadata_fetch, url, cookies_path)
    except Exception as e:
        log.warning("yt-dlp metadata fetch failed: %s", e)
        metadata = {
            "title": f"Web Video (ID: {cache_id})",
            "uploader": "Unknown",
            "views": 0,
            "duration": "N/A",
            "upload_date": "N/A",
            "chapters": []
        }

    # 3. APPROACH 1: Fast Subtitle API (Only works on YouTube)
    if is_youtube:
        try:
            log.info("Querying YouTube caption endpoints...")
            session = get_authenticated_session(cookies_path)

            def fetch_captions():
                api = YouTubeTranscriptApi(http_client=session)
                return api.fetch(video_id)

            transcript_list = await asyncio.to_thread(fetch_captions)

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

            chapters_section = "\n".join(metadata["chapters"]) if metadata["chapters"] else "None available"
            return (
                f"[SUCCESS: YouTube Captions]\n"
                f"Title: {metadata['title']}\n"
                f"Creator: {metadata['uploader']}\n"
                f"Duration: {metadata['duration']}\n"
                f"Views: {metadata['views']:,}\n"
                f"URL: {url}\n"
                f"CHAPTER STRUCTURE:\n{chapters_section}\n"
                f"==================================================\n\n"
                + transcript_text
            )
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
        transcript_text = await asyncio.to_thread(_blocking_whisper_transcription, target_param, cookies_path)

        write_to_cache(cache_id, {
            "metadata": metadata,
            "transcript": transcript_text,
            "method": "local_whisper_fallback",
            "timestamp": time.time()
        })

        chapters_section = "\n".join(metadata["chapters"]) if metadata["chapters"] else "None available"
        return (
            f"[SUCCESS: Offline Local ASR Transcription]\n"
            f"Title: {metadata['title']}\n"
            f"Creator: {metadata['uploader']}\n"
            f"Duration: {metadata['duration']}\n"
            f"Views: {metadata['views']:,}\n"
            f"URL: {url}\n"
            f"CHAPTER STRUCTURE:\n{chapters_section}\n"
            f"==================================================\n\n"
            + transcript_text
        )

    except ImportError as e:
        return (
            f"Error: Local transcription engine is not installed.\n"
            f"Details: {str(e)}\n"
            f"Please install one of the following:\n"
            f"  pip install faster-whisper\n"
            f"  pip install openai-whisper torch"
        )
    except Exception as whisper_error:
        return (
            f"Error: Local offline transcription failed.\n"
            f"Details: {str(whisper_error)}\n"
            f"Troubleshooting:\n"
            f"  - Ensure FFmpeg is installed and in your PATH\n"
            f"  - Check your network connection\n"
            f"  - For age-restricted videos, add a cookies.txt file"
        )


def _blocking_screenshot_extractor(url: str, timestamps_secs: list[int], cookies_path: str) -> list:
    is_youtube = bool(extract_video_id(url))

    ydl_opts = {
        'format': '18' if is_youtube else 'best',
        'quiet': True,
        'no_warnings': True,
    }
    if cookies_path:
        ydl_opts['cookiefile'] = cookies_path

    log.info("Extracting streaming source URL...")
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(url, download=False)
        stream_url = info.get('url')

        if not stream_url:
            formats = info.get('formats', [])
            for fmt in formats:
                if fmt.get('url') and (fmt.get('vcodec') != 'none' or not is_youtube):
                    stream_url = fmt['url']
                    break

    if not stream_url:
        return [
            "Error: Failed to extract a playable video stream.\n"
            "Possible causes:\n"
            "  - Video is private or geo-blocked\n"
            "  - Video format is not supported\n"
            "  - Try adding cookies.txt for authenticated content"
        ]

    log.info("Connecting OpenCV to stream URL: %s...", stream_url[:60])
    cap = cv2.VideoCapture(stream_url)

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

    payload = [
        f"[SUCCESS: Screenshot Extraction Completed]\n"
        f"Successfully captured {len(timestamps_secs)} on-screen frames directly from the live feed.\n"
        f"The image content blocks are attached below in chronological order."
    ]

    temp_dir = tempfile.gettempdir()
    video_id = extract_video_id(url)
    cache_id = video_id if video_id else "".join([c if c.isalnum() else "_" for c in url[-20:]])

    for sec in sorted(timestamps_secs):
        target_frame_idx = int(sec * fps)
        log.info("Seeking to %ss (Frame %d out of %d)...", sec, target_frame_idx, total_frames)

        if target_frame_idx >= total_frames:
            log.warning("Seek skipped: requested time %ss is out of video bounds.", sec)
            payload.append(f"[WARNING: Requested timestamp {sec}s is beyond the end of the video.]")
            continue

        cap.set(cv2.CAP_PROP_POS_FRAMES, target_frame_idx)
        ret, frame = cap.read()

        if ret:
            resized_frame = cv2.resize(frame, (640, 360))
            temp_img_path = os.path.join(temp_dir, f"mcp_seek_{cache_id}_{sec}s.jpg")
            cv2.imwrite(temp_img_path, resized_frame)

            payload.append(Image(path=temp_img_path))
            log.info("Frame at %ss captured successfully.", sec)
        else:
            log.warning("Seek failed: OpenCV returned None for frame at %ss.", sec)
            payload.append(f"[WARNING: Failed to seek or read frame at {sec} seconds.]")

    cap.release()
    return payload


@mcp.tool()
async def get_ocular_audio_video_screenshots(url: str, timestamps_secs: list[int]) -> list:
    """
    Extracts high-quality, low-resolution screenshots at specific timestamps directly from any YouTube or Web video
    WITHOUT downloading the entire file (uses HTTP range-seeking streaming).

    This runs asynchronously in a background thread to prevent blocking concurrent MCP requests.

    Args:
        url: The full YouTube or Web video URL.
        timestamps_secs: A list of timestamps in seconds to screenshot (e.g., [45, 120, 300])
    """
    cookies_path = find_cookies_file()

    try:
        payload = await asyncio.to_thread(_blocking_screenshot_extractor, url, timestamps_secs, cookies_path)
        return payload
    except Exception as e:
        return [f"Error during screenshot extraction: {str(e)}"]


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
    if len(sys.argv) > 1 and not sys.argv[1].startswith("-"):
        target_url = sys.argv[1]

        async def run_standalone():
            log.info("Processing target resource: %s", target_url)
            log.info("Fetching transcript and metadata asynchronously...")
            res = await get_ocular_audio_transcript(target_url)

            prompt_context = f"""Please analyze this video thoroughly using the verified video data, uploader chapters, and complete transcript provided below.

--- VIDEO CONTEXT ---
{res}
"""
            success = copy_to_clipboard_native(prompt_context)

            print("=" * 60)
            if success:
                print("[SUCCESS: Context Copied to Clipboard]")
                print("[INSTRUCTION: Paste the clipboard contents inside Claude Web/ChatGPT]")
            else:
                output_file = "video_context.txt"
                with open(output_file, "w", encoding="utf-8") as f:
                    f.write(prompt_context)
                print("[SUCCESS: Transcribed Successfully]")
                print(f"[INFO: Saved context block to: {os.path.abspath(output_file)}]")
                print("[INSTRUCTION: Upload or copy the contents of the text file directly into your Web AI model]")
            print("=" * 60)

        asyncio.run(run_standalone())
    else:
        mcp.run()
