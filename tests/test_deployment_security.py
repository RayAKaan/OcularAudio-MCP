import os
import unittest
from unittest.mock import patch

from deployment_security import (
    StaticBearerTokenVerifier,
    build_auth_settings,
    load_deployment_security,
)


class DeploymentSecurityTests(unittest.IsolatedAsyncioTestCase):
    def test_default_is_local_and_secret_free(self):
        with patch.dict(os.environ, {}, clear=True):
            config = load_deployment_security()
        self.assertFalse(config.require_auth)
        self.assertFalse(config.auth_configured)
        self.assertFalse(config.public_summary()["secret_exposed"])
        self.assertEqual([], list(config.allowed_hosts))

    def test_auth_requires_secret(self):
        with patch.dict(os.environ, {"OCULAR_AUDIO_MCP_REQUIRE_AUTH": "true"}, clear=True):
            with self.assertRaises(ValueError):
                load_deployment_security()

    def test_auth_configuration_and_metadata(self):
        env = {
            "OCULAR_AUDIO_MCP_REQUIRE_AUTH": "true",
            "OCULAR_AUDIO_MCP_AUTH_TOKEN": "test-secret",
            "OCULAR_AUDIO_MCP_ISSUER_URL": "https://issuer.example",
            "OCULAR_AUDIO_MCP_RESOURCE_URL": "https://mcp.example/mcp",
            "OCULAR_AUDIO_MCP_REQUIRED_SCOPES": "mcp:read,mcp:analyze",
            "OCULAR_AUDIO_MCP_ALLOWED_HOSTS": "mcp.example,mcp.example:*",
            "OCULAR_AUDIO_MCP_ALLOWED_ORIGINS": "https://app.example",
            "OCULAR_AUDIO_MCP_TOKEN_TTL": "120",
        }
        with patch.dict(os.environ, env, clear=True):
            config = load_deployment_security()
            auth = build_auth_settings(config)
            summary = config.public_summary()
        self.assertTrue(config.require_auth)
        self.assertTrue(config.auth_configured)
        self.assertIsNotNone(auth)
        self.assertEqual(["mcp:read", "mcp:analyze"], list(config.required_scopes))
        self.assertEqual(["mcp.example", "mcp.example:*"], list(config.allowed_hosts))
        self.assertEqual(120, summary["token_ttl_seconds"])
        self.assertNotIn("test-secret", str(summary))

    async def test_static_verifier_accepts_only_configured_token(self):
        verifier = StaticBearerTokenVerifier(
            "test-secret", "https://mcp.example/mcp", ("mcp:read",), 60
        )
        valid = await verifier.verify_token("test-secret")
        invalid = await verifier.verify_token("wrong")
        self.assertIsNotNone(valid)
        self.assertEqual("ocular-audio-operator", valid.subject)
        self.assertEqual(["mcp:read"], valid.scopes)
        self.assertIsNone(invalid)


if __name__ == "__main__":
    unittest.main()
