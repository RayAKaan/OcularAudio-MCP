# Docker deployment defaults

The Compose deployment is intentionally local-only by default:

- The host port is published on `127.0.0.1`, not every network interface.
- The application runs as UID/GID `10001`, with its cache volume mounted under its home directory.
- The container uses a read-only root filesystem, a bounded PID count, a writable temporary filesystem, dropped Linux capabilities, and `no-new-privileges`.
- The Compose healthcheck currently confirms that the HTTP listener accepts TCP connections; it is a process/listener check, not an authenticated MCP readiness check.

## Start locally

```sh
cp .env.example .env
docker compose -f docker/docker-compose.yml up --build -d
```

The service is available at `http://127.0.0.1:8000/mcp`.

## Expose beyond localhost

Do not change the port binding to `0.0.0.0` unless you have configured authentication and an appropriate host/origin allowlist. Set `OCULAR_AUDIO_MCP_REQUIRE_AUTH=true`, provide a long random `OCULAR_AUDIO_MCP_AUTH_TOKEN`, and configure the issuer, resource URL, allowed hosts, and allowed origins for the actual deployment. Put TLS and an identity-aware reverse proxy in front of internet-facing deployments. The built-in static bearer token is intended for controlled deployments, not as a substitute for an organization identity provider.
