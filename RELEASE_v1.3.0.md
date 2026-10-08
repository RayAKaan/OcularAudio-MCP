# OcularAudio MCP v1.3.0 Release

v1.3.0 is the complete production-oriented OcularAudio release: universal media resolution, timestamped evidence retrieval, visual/OCR evidence, hybrid and multimodal analysis, batch intelligence, deterministic agentic orchestration, capability modes, MCP v2 interoperability, Streamable HTTP, deployment security, readiness, bounded metrics, and audit retention.

## NPM package

`ocular-audio-mcp@1.3.0`

Build and inspect:

```bash
npm install
npm run check
npm pack
```

Publish only after inspecting the tarball:

```bash
npm publish ocular-audio-mcp-1.3.0.tgz --access public
```

The package includes the Node CLI, Python MCP server, and runtime modules. Python, FFmpeg, and optional OCR/Whisper runtime prerequisites remain external.

## Production deployment

```bash
cp .env.example .env
# Configure a strong auth token, real resource/issuer URLs, host and origin allowlists.
docker compose -f docker/docker-compose.yml up --build -d
```

Local stdio remains the default and does not require HTTP authentication.

## Release gate

- All version metadata: 1.3.0.
- CI: green.
- NPM metadata: `npm run check`.
- Package: `npm pack`.
- Deployment: Docker build/startup and authenticated MCP smoke test.
