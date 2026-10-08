# OcularAudio MCP

**Universal local-first media intelligence for AI agents.**

OcularAudio lets MCP-compatible AI systems watch, listen to, search, inspect, compare, and reason over media. It turns URLs, streams, and local media into reusable timestamped evidence: metadata, transcripts, frames, OCR, retrieval results, multimodal moments, and cross-video intelligence.

**v1.3.0 · MIT**

## Product

### What it does
- **Universal media intake:** web URLs, direct media, local files, live/stream sources, and a broad set of social, video, audio and archive platforms.
- **Speech understanding:** timestamped captions with local Whisper fallback when captions are unavailable.
- **Visual understanding:** intelligent screenshots, exact frames, frame bursts, crops, visual indexing and perceptual similarity.
- **On-screen text:** optional Tesseract OCR produces searchable visual text evidence.
- **Evidence search:** timestamp-aware lexical, semantic and hybrid retrieval instead of forcing agents to consume entire media files.
- **Multimodal analysis:** aligns transcript, visual and OCR evidence around the same moments.
- **Batch intelligence:** process multiple sources, search across them, and generate cross-video comparisons with failure isolation.
- **Agentic execution:** turn analysis requests into bounded plans with retries, timeouts, audit records and health reporting.
- **Capability modes:** Lite, Intelligence, Deep and Auto control processing depth and response richness.
- **Local caching:** reuse processed evidence and manage cache state through CLI or MCP.
- **Operational awareness:** capabilities, health, readiness, security state, metrics and the full protocol contract are machine-readable.
- **MCP interoperability:** tools, resources and prompts over stdio or Streamable HTTP.
- **Production deployment:** bearer-token protection, host/origin controls, Docker deployment, persistent cache and readiness checks.

### Best use cases
Research and lecture analysis · product demonstrations · competitor analysis · interviews · technical talks · UI walkthroughs · multi-video comparison · evidence-grounded AI investigation.

## Capability matrix

| Capability | User outcome |
|---|---|
| Universal sources | Analyze URLs, files and streams through one interface |
| Transcript evidence | Find exactly when something was said |
| Visual evidence | Inspect what was shown at a timestamp |
| OCR | Search text visible inside video frames |
| Hybrid retrieval | Combine speech and visual evidence |
| Multimodal moments | Understand speech and visuals together |
| Batch analysis | Investigate collections of videos |
| Cross-video comparison | Compare evidence across sources |
| Agentic workflows | Execute bounded evidence investigations |
| Capability modes | Trade speed for analysis depth |
| Cache | Make repeated analysis faster |
| MCP prompts | Start common investigation workflows |
| MCP resources | Give hosts operational context |
| HTTP deployment | Run as a protected network service |

## Quick start

### NPM / MCP

    npx -y ocular-audio-mcp

Local MCP hosts can launch the same command. Example:

    {
      "mcpServers": {
        "ocular-audio": {
          "command": "npx",
          "args": ["-y", "ocular-audio-mcp"]
        }
      }
    }

Claude Code:

    claude mcp add ocular-audio -- npx -y ocular-audio-mcp

Codex CLI:

    codex mcp add ocular-audio -- npx -y ocular-audio-mcp

### Direct CLI

    npx ocular-audio "https://www.youtube.com/watch?v=dQw4w9WgXcQ"
    npx ocular-audio --check
    npx ocular-audio --json "URL"
    npx ocular-audio --visual-index --ocr "URL"
    npx ocular-audio --multimodal-search "pricing" "URL"
    npx ocular-audio --plan "Find the pricing discussion and inspect its visual evidence"
    npx ocular-audio --agentic "Find every pricing discussion and inspect the relevant slides"

## Technical overview

    MCP host / agent
            |
    MCP tools + prompts + resources
            |
    Universal source resolver
            |
    Evidence: metadata + transcript + timestamps + chapters
          /   |   \
    visual  OCR  retrieval
          \   |   /
       multimodal moments
             |
       batch intelligence
             |
       agentic execution
             |
       operations / audit / readiness

### Core modules
- media_resolver.py + universal_sources.py: source classification, platform families, streams, local media and analysis policy.
- evidence_index.py: timestamped evidence segmentation, chapter association and deterministic retrieval.
- visual_index.py: frame sampling, bursts, crops, perceptual hashes, descriptors and OCR evidence.
- semantic_index.py: local TF-IDF/lexical/semantic and hybrid retrieval.
- multimodal_index.py: transcript/visual/OCR timestamp alignment and ranking.
- batch_index.py: bounded multi-source execution, persistence, search and comparison.
- agentic_index.py: deterministic planning, retries, timeouts, audit records and execution health.
- capability_modes.py: Lite, Intelligence, Deep and Auto policy resolution.
- protocol_contract.py: machine-readable MCP interoperability contract.
- deployment_security.py: controlled HTTP authentication and transport security.
- runtime_ops.py: bounded metrics, latency observations, readiness and audit retention.

## MCP surface

### 32 tools
Media/evidence: get_ocular_audio_transcript, get_ocular_audio_video_context, search_ocular_audio_video, get_ocular_audio_video_timeline, inspect_ocular_audio_moment, get_ocular_audio_metadata, get_ocular_audio_chapters, inspect_ocular_audio_source, get_ocular_audio_capabilities.

Visual/OCR: get_ocular_audio_video_screenshots, index_ocular_audio_video_visuals, search_ocular_audio_visuals, get_ocular_audio_video_frame, get_ocular_audio_video_frame_burst, crop_ocular_audio_video_frame.

Retrieval/multimodal: search_ocular_audio_hybrid, analyze_ocular_audio_multimodal, inspect_ocular_audio_multimodal_moment, search_ocular_audio_cache.

Batch: analyze_ocular_audio_batch, search_ocular_audio_videos, compare_ocular_audio_videos, get_ocular_audio_batch, list_ocular_audio_batches.

Agentic/operations: plan_ocular_audio_analysis, run_ocular_audio_analysis, get_ocular_audio_health, get_ocular_audio_audit, get_ocular_audio_contract, get_ocular_audio_identity.

Cache: list_ocular_audio_cache, clear_ocular_audio_cache.

### 7 resources
- ocularaudio://capabilities
- ocularaudio://modes
- ocularaudio://health
- ocularaudio://contract
- ocularaudio://security
- ocularaudio://readiness
- ocularaudio://metrics

### 4 prompts
- inspect_video
- search_video_evidence
- review_visual_evidence
- compare_videos

## Deployment

### Local stdio
stdio is the default local MCP transport and requires no HTTP authentication.

### Streamable HTTP
    npx ocular-audio --transport streamable-http --host 127.0.0.1 --port 8000

The MCP endpoint is /mcp. For network exposure, configure authentication, real issuer/resource URLs, allowed hosts and allowed origins. Do not expose an unauthenticated instance to an untrusted network.

### Docker
    cp .env.example .env
    docker compose -f docker/docker-compose.yml up --build -d

The supplied deployment uses Python 3.11, FFmpeg, a persistent cache volume, a read-only container filesystem, dropped capabilities, no-new-privileges, restart policy and a healthcheck.

For internet-facing deployments, use TLS and an organization identity provider. The built-in static bearer verifier is intended for controlled deployments and can be replaced by JWT validation or RFC 7662 introspection.

## Runtime requirements
- Python 3.11+ recommended for the release environment.
- Node.js 18+ for the NPM CLI.
- FFmpeg for media processing.
- OpenCV for visual processing.
- faster-whisper for local transcription fallback.
- Tesseract is optional for OCR.
- Network access is required for remote sources.

The NPM package does not hide native Python/system prerequisites; OcularAudio is a local media-processing server rather than a hosted API.

## Cookies and restricted media
Operator-supplied cookies.txt can be used for sources that require an authenticated browser session. Never commit cookies, access tokens or credentials.

## Release v1.3.0

    npm install
    npm run check
    npm pack

This creates ocular-audio-mcp-1.3.0.tgz. Inspect it before publishing:

    npm publish ocular-audio-mcp-1.3.0.tgz --access public

See RELEASE_v1.3.0.md. A manual GitHub Actions workflow can also build and upload the exact tarball as an artifact.

## Validation

    python -m unittest discover -s tests -v
    node --check bin/cli.js
    npm run check

CI additionally validates the MCP SDK surface, tool/resource/prompt registration, Streamable HTTP authorization behavior, compilation, CLI syntax and package metadata.

## Design principles
- **Local-first:** no mandatory cloud inference API.
- **Evidence-first:** preserve timestamps and source evidence.
- **Composable:** each analysis layer builds on the previous evidence layer.
- **Bounded:** steps, retries, concurrency, metrics cardinality and audit retention have explicit limits.
- **MCP-native:** tools, resources and prompts are protocol primitives.
- **Deterministic infrastructure:** OcularAudio provides execution/evidence primitives while the host remains responsible for model-level reasoning.

## License
MIT. See LICENSE.
