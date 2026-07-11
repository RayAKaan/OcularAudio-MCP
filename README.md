# OcularAudio MCP

An asynchronous Model Context Protocol (MCP) server that gives AI models "eyes and ears" to process web videos. It extracts transcripts and captures screenshots from YouTube and other video platforms.

## Features

- **Hybrid transcript extraction**: Fetches YouTube captions instantly, falls back to local Whisper ASR
- **On-demand video screenshots**: Captures frames at any timestamp without downloading the full video
- **Cookie authentication**: Supports age-restricted and private videos via cookies.txt
- **Local caching**: Processed videos are cached for instant subsequent lookups
- **Async architecture**: Non-blocking design keeps MCP clients responsive

## Requirements

- **Python 3.9+** (required for `list[int]` type hints)
- **FFmpeg** (required by yt-dlp and OpenCV)
- **Node.js 18+** (only for the CLI wrapper)

## Installation

### 1. Install system dependencies

**macOS:**
```bash
brew install ffmpeg python3
```

**Windows:**
```bash
choco install ffmpeg python
```

**Linux:**
```bash
sudo apt update && sudo apt install ffmpeg python3 python3-pip
```

### 2. Install Python packages

```bash
pip install -r requirements.txt
```

Or manually:
```bash
pip install mcp youtube-transcript-api yt-dlp opencv-python-headless faster-whisper requests
```

### 3. Install Node.js CLI (optional)

```bash
npm install
```

## Usage

### Option A: MCP Server (for Claude Desktop, Cursor, etc.)

Add to your MCP client configuration (e.g. `claude_desktop_config.json`):

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

**Windows example:**
```json
{
  "mcpServers": {
    "ocular-audio-mcp": {
      "command": "python",
      "args": ["C:\\Users\\You\\OcularAudio-MCP\\ocular_audio_mcp.py"]
    }
  }
}
```

### Option B: CLI (for web-based AI models)

```bash
npx ocular-audio "https://www.youtube.com/watch?v=dQw4w9WgXcQ"
```

The transcript is automatically copied to your clipboard. Paste it into Claude Web, ChatGPT, or any AI chat.

**CLI options:**
```
npx ocular-audio --help       # Show usage
npx ocular-audio --version    # Show version
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

### `get_ocular_audio_transcript`

Extracts transcript, chapters, and metadata from a video.

**Parameters:**
- `url` (string): Video URL
- `use_local_whisper` (boolean, default: true): Enable Whisper fallback if captions unavailable

### `get_ocular_audio_video_screenshots`

Captures screenshots at specific timestamps.

**Parameters:**
- `url` (string): Video URL
- `timestamps_secs` (array of integers): Timestamps to capture (e.g., `[45, 120, 300]`)

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
