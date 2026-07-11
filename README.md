# OcularAudio MCP

![OcularAudio MCP](OcularAudioMCP.png)

An asynchronous Model Context Protocol (MCP) server that gives AI models "eyes and ears" to process web videos. It extracts transcripts and captures screenshots from YouTube and other video platforms.

## Features

- **Hybrid transcript extraction**: Fetches YouTube captions instantly, falls back to local Whisper ASR
- **On-demand video screenshots**: Captures frames at any timestamp without downloading the full video
- **OCR on screenshots**: Extract visible text from frames using Tesseract (optional, `--ocr` flag)
- **Cookie authentication**: Supports age-restricted and private videos via cookies.txt
- **Local caching**: Processed videos are cached for instant subsequent lookups
- **Async architecture**: Non-blocking design keeps MCP clients responsive
- **Flexible output**: Clipboard, stdout, file, or JSON — your choice

## Requirements

- **Python 3.9+** (required for `list[int]` type hints)
- **FFmpeg** (required by yt-dlp and OpenCV)
- **Node.js 18+** (only for the CLI wrapper)
- **Tesseract** (optional, only for `--ocr` flag)

## Installation

### 1. Install system dependencies

**macOS:**
```bash
brew install ffmpeg python3
# Optional (for OCR):
brew install tesseract
```

**Windows:**
```bash
choco install ffmpeg python
# Optional (for OCR):
choco install tesseract
```

**Linux:**
```bash
sudo apt update && sudo apt install ffmpeg python3 python3-pip
# Optional (for OCR):
sudo apt install tesseract-ocr
```

### 2. Install Python packages

```bash
pip install -r requirements.txt
```

Or manually:
```bash
pip install mcp youtube-transcript-api yt-dlp opencv-python-headless faster-whisper requests pytesseract
```

### 3. Install Node.js CLI (optional)

```bash
npm install
```

## Usage

### Option A: MCP Server (Recommended)

The MCP server gives AI models direct access to video transcripts and screenshots.

**Quick Install** — No installation needed. Just add the config to your MCP client below.

#### Claude Desktop

```json
{
  "mcpServers": {
    "ocular-audio-mcp": {
      "command": "npx",
      "args": ["ocular-audio-mcp"]
    }
  }
}
```
Config: `~/Library/Application Support/Claude/claude_desktop_config.json` (macOS) or `%APPDATA%\Claude\claude_desktop_config.json` (Windows)

#### Cursor

```json
{
  "mcpServers": {
    "ocular-audio-mcp": {
      "command": "npx",
      "args": ["ocular-audio-mcp"]
    }
  }
}
```
Config: `.cursor/mcp.json` (project) or `~/.cursor/mcp.json` (global)

#### Claude Code

```bash
claude mcp add ocular-audio-mcp -- npx ocular-audio-mcp
```

#### Codex CLI (OpenAI)

```bash
codex mcp add ocular-audio-mcp -- npx ocular-audio-mcp
```

#### Gemini CLI

```bash
gemini mcp add ocular-audio-mcp npx ocular-audio-mcp --scope user
```

#### Windsurf

```json
{
  "mcpServers": {
    "ocular-audio-mcp": {
      "command": "npx",
      "args": ["ocular-audio-mcp"]
    }
  }
}
```
Config: `~/.codeium/windsurf/mcp_config.json`

#### Zed

```json
{
  "context_servers": {
    "ocular-audio-mcp": {
      "command": "npx",
      "args": ["ocular-audio-mcp"]
    }
  }
}
```
Config: `~/.config/zed/settings.json`

#### VS Code (GitHub Copilot)

```json
{
  "servers": {
    "ocular-audio-mcp": {
      "type": "stdio",
      "command": "npx",
      "args": ["ocular-audio-mcp"]
    }
  }
}
```
Config: `.vscode/mcp.json`

#### OpenCode

```json
{
  "mcpServers": {
    "ocular-audio-mcp": {
      "command": "npx",
      "args": ["ocular-audio-mcp"]
    }
  }
}
```
Config: `~/.opencode/config.json`

#### Cline (VS Code Extension)

```json
{
  "mcpServers": {
    "ocular-audio-mcp": {
      "command": "npx",
      "args": ["ocular-audio-mcp"]
    }
  }
}
```

#### Local Development (from source)

```json
{
  "mcpServers": {
    "ocular-audio-mcp": {
      "command": "python",
      "args": ["/path/to/ocular_audio_mcp.py"]
    }
  }
}
```

### Option B: CLI

```bash
npx ocular-audio "https://www.youtube.com/watch?v=dQw4w9WgXcQ"
```

By default, the transcript is printed to stdout and copied to your clipboard. Paste it into Claude Web, ChatGPT, or any AI chat.

#### CLI Options

| Flag | Description |
|------|-------------|
| `-h`, `--help` | Show help message |
| `-v`, `--version` | Show version number |
| `--stdout` | Print transcript to stdout only (no clipboard, no file) |
| `--no-clipboard` | Skip clipboard copy |
| `--output <file>` | Write context to a specific file path |
| `--json` | Output raw JSON (metadata + transcript) for programmatic use |
| `--detail <level>` | Screenshot capture mode: `overview`, `balanced`, `deep`, `auto` (default: `auto`) |
| `--ocr` | Extract text from screenshots using Tesseract OCR |
| `--force` | Bypass cache and re-process the video |
| `--verbose` | Show detailed progress information |
| `--quiet` | Suppress summary and status messages |
| `--check` | Check system dependencies (Python, FFmpeg, Whisper, Tesseract) |
| `--list-cached` | List all cached videos with titles |
| `--cache-info` | Show cache statistics (count, size, oldest/newest) |
| `--clear-cache` | Delete all cached transcripts and screenshots |

#### Examples

```bash
# Basic usage — prints to stdout + copies to clipboard
npx ocular-audio "https://www.youtube.com/watch?v=dQw4w9WgXcQ"

# Stdout only — great for piping to other tools
npx ocular-audio --stdout "https://www.youtube.com/watch?v=dQw4w9WgXcQ" | head -50

# Write to a specific file
npx ocular-audio --output transcript.txt "https://www.youtube.com/watch?v=dQw4w9WgXcQ"

# Raw JSON for programmatic consumption
npx ocular-audio --json "https://www.youtube.com/watch?v=dQw4w9WgXcQ" | jq .metadata.title

# Transcript only, no screenshots
npx ocular-audio --detail overview "https://www.youtube.com/watch?v=dQw4w9WgXcQ"

# Maximum screenshots
npx ocular-audio --detail deep "https://www.youtube.com/watch?v=dQw4w9WgXcQ"

# No clipboard copy, just print to terminal
npx ocular-audio --no-clipboard "https://www.youtube.com/watch?v=dQw4w9WgXcQ"

# Screenshots with OCR — extract visible text from frames
npx ocular-audio --ocr "https://www.youtube.com/watch?v=dQw4w9WgXcQ"

# JSON output with OCR
npx ocular-audio --json --ocr "https://www.youtube.com/watch?v=dQw4w9WgXcQ"

# Force re-process (bypass cache)
npx ocular-audio --force "https://www.youtube.com/watch?v=dQw4w9WgXcQ"

# Verbose mode — see all progress details
npx ocular-audio --verbose "https://www.youtube.com/watch?v=dQw4w9WgXcQ"

# Quiet mode — minimal output
npx ocular-audio --quiet --stdout "https://www.youtube.com/watch?v=dQw4w9WgXcQ"

# Check system capabilities
npx ocular-audio --check

# List cached videos
npx ocular-audio --list-cached

# Show cache stats
npx ocular-audio --cache-info

# Clear all cached data
npx ocular-audio --clear-cache
```

## Cookie Setup (for age-restricted/private videos)

YouTube may block transcript access for age-restricted or private videos. To fix this, export your browser cookies:

1. Install a browser extension like "Get cookies.txt LOCALLY" (Chrome/Firefox)
2. Go to youtube.com while logged in
3. Export cookies to a file named `cookies.txt`
4. Place the file in one of these locations:
   - `~/.cache/ocular_audio_mcp/cookies.txt`
   - `~/.config/ocular_audio_mcp/cookies.txt`
   - `./cookies.txt` (in the project directory)

The server will automatically detect and use the cookies file.

## MCP Tools

### `get_ocular_audio_capabilities`

Returns system capabilities and dependency status. Use this to check what features are available.

**Parameters:** None

**Returns:** System info including Python version, FFmpeg, Whisper, Tesseract, OpenCV, and cookie status.

### `get_ocular_audio_metadata`

Extracts only video metadata (title, creator, duration, views, chapters) without transcript. Much faster than getting the full transcript.

**Parameters:**
- `url` (string): Video URL

### `get_ocular_audio_transcript`

Extracts the complete transcript, video chapters, and metadata from a video.

**Parameters:**
- `url` (string): Video URL
- `use_local_whisper` (boolean, default: true): Enable Whisper fallback if captions unavailable

### `get_ocular_audio_chapters`

Extracts only video chapters with timestamps. Returns chapter titles with start times in [MM:SS] format.

**Parameters:**
- `url` (string): Video URL

### `get_ocular_audio_video_screenshots`

Captures screenshots at specific timestamps.

**Parameters:**
- `url` (string): Video URL
- `timestamps_secs` (array of integers): Timestamps to capture (e.g., `[45, 120, 300]`)
- `enable_ocr` (boolean, default: false): If true, run OCR on each captured frame to extract visible text

### `get_ocular_audio_video_context`

Extracts transcript, metadata, and intelligent screenshots in one call. Automatically analyzes the transcript to find visually important moments and captures screenshots at those timestamps.

**Parameters:**
- `url` (string): Video URL
- `detail_level` (string, default: "auto"): Controls screenshot capture mode:
  - `"auto"` - Adapts to video length and content importance
  - `"overview"` - Transcript and metadata only, no screenshots (fastest)
  - `"balanced"` - Screenshots only at visually important moments (strong signals)
  - `"deep"` - Screenshots at every visually significant moment (all signals)
- `use_local_whisper` (boolean, default: true): Enable Whisper fallback if captions unavailable
- `enable_ocr` (boolean, default: false): If true, run OCR on captured screenshots to extract visible text

### `list_ocular_audio_cache`

Lists all cached videos with their metadata (title, uploader, duration, when cached).

**Parameters:** None

### `clear_ocular_audio_cache`

Clears cached video data.

**Parameters:**
- `video_id` (string, optional): Video ID to clear specific video. If empty, clears all cache.

## Cache Management

Processed videos are cached in `~/.cache/ocular_audio_mcp/` for 7 days. Use the CLI flags to manage the cache:

```bash
npx ocular-audio --list-cached     # See what's cached
npx ocular-audio --cache-info      # Storage stats
npx ocular-audio --clear-cache     # Wipe everything
```

Or manually:
```bash
rm -rf ~/.cache/ocular_audio_mcp/*.json
```

## Troubleshooting

### "No local ASR engines found"
Install a Whisper engine:
```bash
pip install faster-whisper
```

### "Audio track download failed"
- Check your network connection
- For age-restricted videos, add a cookies.txt file (see Cookie Setup above)
- Ensure FFmpeg is installed: `ffmpeg -version`

### "Failed to extract a playable video stream"
- The video may be private or geo-blocked
- Try adding cookies.txt
- Check if the video is still available

### Python not found on Windows
Ensure Python is in your PATH. Try:
```bash
python --version
```
If not found, reinstall Python from python.org and check "Add Python to PATH" during installation.

### MCP server not connecting
- Verify the path in your MCP client config is correct
- Test the server manually: `python /path/to/ocular_audio_mcp.py`
- Check that all dependencies are installed: `pip list | grep -E "mcp|whisper|yt-dlp"`

## License

MIT
