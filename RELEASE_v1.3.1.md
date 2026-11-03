# OcularAudio MCP v1.3.1 Release

This maintenance release consolidates the MCP protocol, container deployment, and package-artifact reliability work completed after v1.3.0.

## Changes

- Exercise the Node CLI through a complete MCP stdio initialize, tools/list, and real tools/call round trip.
- Harden Docker defaults with a dedicated non-root runtime, a read-only root filesystem, dropped capabilities, no-new-privileges, bounded PIDs, and localhost-only port publishing.
- Verify authenticated Streamable HTTP MCP initialization in the actual Docker Compose healthcheck.
- Run Docker Compose build/startup and authenticated readiness validation in CI.
- Build the npm tarball as an isolated consumer, verify its required contents, and check the packed CLI version and help output.
- Generate and verify a SHA-256 checksum for the release tarball.

## Version metadata

The source package, lockfile, and MCP server metadata are version **1.3.1**.

The MCP registry package entry intentionally remains pinned to **1.2.1**, the published npm artifact verified by CI. The 1.3.1 source package is not published by this change.

## Build and inspect

```bash
npm ci
npm run check
npm run verify:package
npm pack
sha256sum ocular-audio-mcp-1.3.1.tgz
```

The manual GitHub Actions release workflow builds the tarball, verifies its SHA-256 checksum, and uploads both files as an artifact. Publishing to npm is a separate, explicit release step.

## Deployment

```bash
cp .env.example .env
# Configure authentication and deployment-specific host/origin settings.
docker compose -f docker/docker-compose.yml up --build -d
```

Local stdio remains the default and does not require HTTP authentication.
