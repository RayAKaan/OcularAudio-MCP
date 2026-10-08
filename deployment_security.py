"""Phase 12 deployment and transport security configuration.

All HTTP security is opt-in through environment variables so the local stdio
workflow remains unchanged. Secrets are never stored in source control.
"""

from __future__ import annotations

import os
import time
from dataclasses import dataclass
from urllib.parse import urlparse

from mcp.server.auth.provider import AccessToken, TokenVerifier
from mcp.server.auth.settings import AuthSettings
from pydantic import AnyHttpUrl


def _csv(name: str) -> list[str]:
    return [item.strip() for item in os.getenv(name, "").split(",") if item.strip()]


def _required_url(name: str, default: str) -> str:
    value = os.getenv(name, default).strip()
    parsed = urlparse(value)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ValueError(f"{name} must be an absolute http(s) URL")
    return value.rstrip("/")


@dataclass(frozen=True)
class DeploymentSecurity:
    require_auth: bool
    auth_token: str | None
    issuer_url: str
    resource_server_url: str
    required_scopes: tuple[str, ...]
    allowed_hosts: tuple[str, ...]
    allowed_origins: tuple[str, ...]
    token_ttl_seconds: int = 3600

    @property
    def auth_configured(self) -> bool:
        return bool(self.auth_token)

    def public_summary(self) -> dict[str, object]:
        return {
            "require_auth": self.require_auth,
            "auth_configured": self.auth_configured,
            "issuer_url": self.issuer_url if self.auth_configured else None,
            "resource_server_url": self.resource_server_url if self.auth_configured else None,
            "required_scopes": list(self.required_scopes),
            "allowed_hosts": list(self.allowed_hosts),
            "allowed_origins": list(self.allowed_origins),
            "token_ttl_seconds": self.token_ttl_seconds,
            "secret_exposed": False,
        }


def load_deployment_security() -> DeploymentSecurity:
    token = os.getenv("OCULAR_AUDIO_MCP_AUTH_TOKEN", "").strip() or None
    require_auth = os.getenv("OCULAR_AUDIO_MCP_REQUIRE_AUTH", "").strip().lower() in {
        "1", "true", "yes", "on"
    }
    if require_auth and not token:
        raise ValueError(
            "OCULAR_AUDIO_MCP_REQUIRE_AUTH is enabled but "
            "OCULAR_AUDIO_MCP_AUTH_TOKEN is not configured"
        )

    scopes = tuple(_csv("OCULAR_AUDIO_MCP_REQUIRED_SCOPES") or ["mcp:read"])
    hosts = tuple(_csv("OCULAR_AUDIO_MCP_ALLOWED_HOSTS"))
    origins = tuple(_csv("OCULAR_AUDIO_MCP_ALLOWED_ORIGINS"))
    ttl_raw = os.getenv("OCULAR_AUDIO_MCP_TOKEN_TTL", "3600")
    try:
        ttl = int(ttl_raw)
    except ValueError as exc:
        raise ValueError("OCULAR_AUDIO_MCP_TOKEN_TTL must be an integer") from exc
    if ttl <= 0:
        raise ValueError("OCULAR_AUDIO_MCP_TOKEN_TTL must be greater than zero")

    return DeploymentSecurity(
        require_auth=require_auth,
        auth_token=token,
        issuer_url=_required_url("OCULAR_AUDIO_MCP_ISSUER_URL", "http://127.0.0.1:8000"),
        resource_server_url=_required_url(
            "OCULAR_AUDIO_MCP_RESOURCE_URL", "http://127.0.0.1:8000/mcp"
        ),
        required_scopes=scopes,
        allowed_hosts=hosts,
        allowed_origins=origins,
        token_ttl_seconds=ttl,
    )


class StaticBearerTokenVerifier(TokenVerifier):
    """Minimal resource-server verifier for operator-supplied static tokens.

    This is appropriate for controlled internal deployments. Production systems
    with an identity provider should replace this verifier with JWT validation
    or RFC 7662 introspection.
    """

    def __init__(self, token: str, resource: str, scopes: tuple[str, ...], ttl_seconds: int):
        self._token = token
        self._resource = resource
        self._scopes = list(scopes)
        self._ttl_seconds = ttl_seconds

    async def verify_token(self, token: str) -> AccessToken | None:
        if token != self._token:
            return None
        return AccessToken(
            token=token,
            client_id="ocular-audio-static-client",
            scopes=self._scopes,
            expires_at=int(time.time()) + self._ttl_seconds,
            resource=self._resource,
            subject="ocular-audio-operator",
        )


def build_auth_settings(config: DeploymentSecurity) -> AuthSettings | None:
    if not config.require_auth:
        return None
    return AuthSettings(
        issuer_url=AnyHttpUrl(config.issuer_url),
        resource_server_url=AnyHttpUrl(config.resource_server_url),
        required_scopes=list(config.required_scopes),
        validate_token_resource=True,
    )
