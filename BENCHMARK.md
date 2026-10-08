# OcularAudio MCP — v1.3.0 Benchmark & Capability Report

This document is the release-era benchmark record and capability inventory. It intentionally avoids presenting historical measurements as universal guarantees.

## Current product surface

| Surface | v1.3.0 |
|---|---:|
| MCP tools | 32 |
| MCP resources | 7 |
| MCP prompts | 4 |
| Primary local transport | stdio |
| HTTP transport | Streamable HTTP |
| Analysis modes | Lite / Intelligence / Deep / Auto |
| External telemetry dependency | None |
| Local cache | Yes |
| Batch analysis | Yes |
| Multimodal evidence | Yes |
| Agentic execution | Bounded deterministic planner |

## What is measured

The repository CI measures correctness and protocol behavior rather than claiming a universal media-processing latency.

- Python compilation of all production modules.
- MCP SDK v2 import and surface validation.
- Full unit/integration test discovery.
- MCP tools, resources and prompts registration.
- Streamable HTTP authentication and host-gate behavior.
- Node CLI syntax.
- Package/server version consistency.
- NPM release metadata validation.

## Performance characteristics

Performance depends heavily on source platform, media duration, captions, codec, network conditions, CPU, available memory, Whisper model and OCR workload.

| Workload | Main factors |
|---|---|
| Caption retrieval | source API/network latency |
| Local Whisper | CPU/GPU, model size, audio duration |
| Frame capture | codec, seeking, source duration and frame count |
| OCR | frame resolution and Tesseract processing |
| Retrieval | local corpus size and query complexity |
| Batch | source count, concurrency and slowest source |
| Cache hit | local filesystem performance |

Historical benchmark numbers from early versions have deliberately been removed from the release summary where they no longer describe the current architecture.

## Reliability boundaries

OcularAudio provides bounded execution and graceful failure isolation, but media extraction is inherently dependent on external source behavior.

- Captions can be unavailable or blocked.
- Private/age-restricted media may require valid operator cookies.
- Source extractors can change independently of OcularAudio.
- Live streams can change or terminate while being analyzed.
- Whisper and OCR are optional processing paths with materially higher CPU cost.
- Network deployments require correctly configured authentication and host/origin controls.

## Product comparison guidance

OcularAudio should be evaluated as a **media evidence and intelligence layer for MCP agents**, not as a video editor or hosted transcription API.

Its differentiators are the combination of:
- universal source normalization
- timestamped evidence
- visual and OCR evidence
- hybrid/multimodal retrieval
- cross-video intelligence
- bounded agentic execution
- local caching
- MCP-native tools/resources/prompts
- local-first deployment

## Reproducing release validation

    python -m unittest discover -s tests -v
    node --check bin/cli.js
    npm run check
    npm pack

For deployment validation:

    docker compose -f docker/docker-compose.yml up --build -d

Then validate the configured MCP endpoint and authentication policy before exposing it to a network.

## Benchmark policy

New benchmark claims should include hardware, OS, source URL/type, media duration, network conditions, dependency versions, analysis mode and whether the result was a cache hit. Do not use a single historical measurement as a general performance guarantee.
