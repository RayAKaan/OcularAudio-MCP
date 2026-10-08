import unittest

from mcp.server import MCPServer
from mcp.server.auth.settings import AuthSettings
from mcp.server.transport_security import TransportSecuritySettings
from pydantic import AnyHttpUrl
from starlette.testclient import TestClient

from deployment_security import StaticBearerTokenVerifier


class StreamableHTTPTransportTests(unittest.TestCase):
    def _build_app(self):
        resource = "http://testserver/mcp"
        verifier = StaticBearerTokenVerifier(
            "phase13-secret",
            resource,
            ("mcp:read",),
            3600,
        )
        server = MCPServer(
            "Phase13 Test Server",
            version="1.3.0",
            token_verifier=verifier,
            auth=AuthSettings(
                issuer_url=AnyHttpUrl("https://auth.example.com"),
                resource_server_url=AnyHttpUrl(resource),
                required_scopes=["mcp:read"],
                validate_token_resource=True,
            ),
        )

        @server.tool()
        def health() -> dict[str, str]:
            return {"status": "ok"}

        return server.streamable_http_app(
            transport_security=TransportSecuritySettings(
                allowed_hosts=["testserver"],
            )
        )

    def test_protected_resource_metadata_and_bearer_challenge(self):
        with TestClient(self._build_app()) as client:
            metadata = client.get("/.well-known/oauth-protected-resource/mcp")
            self.assertEqual(200, metadata.status_code)
            payload = metadata.json()
            self.assertEqual("http://testserver/mcp", payload["resource"])
            self.assertEqual(["https://auth.example.com/"], payload["authorization_servers"])

            response = client.post(
                "/mcp",
                json={"jsonrpc": "2.0", "id": 1, "method": "ping"},
            )
            self.assertEqual(401, response.status_code)
            self.assertIn("Bearer", response.headers.get("www-authenticate", ""))
            self.assertIn("resource_metadata", response.headers.get("www-authenticate", ""))

    def test_authenticated_mcp_request_passes_transport_gate(self):
        with TestClient(self._build_app()) as client:
            response = client.post(
                "/mcp",
                headers={
                    "Authorization": "Bearer phase13-secret",
                    "Accept": "application/json, text/event-stream",
                },
                json={"jsonrpc": "2.0", "id": 1, "method": "ping"},
            )
            self.assertNotEqual(401, response.status_code)
            self.assertNotEqual(403, response.status_code)


if __name__ == "__main__":
    unittest.main()
