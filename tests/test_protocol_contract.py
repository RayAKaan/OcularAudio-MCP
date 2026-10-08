import unittest

from protocol_contract import (
    CONTRACT_VERSION,
    MCP_PROTOCOL_REVISION,
    resource_catalog,
    server_contract,
    tool_contract,
    tool_contracts,
    validate_contract,
)


class ProtocolContractTests(unittest.TestCase):
    def test_contract_is_valid(self):
        validate_contract()
        self.assertEqual("1.0", CONTRACT_VERSION)
        self.assertEqual("2026-07-28", MCP_PROTOCOL_REVISION)

    def test_all_tools_have_unique_contracts(self):
        contracts = tool_contracts()
        self.assertEqual(31, len(contracts))
        self.assertEqual(31, len({item["name"] for item in contracts}))

    def test_destructive_cache_tool_is_annotated(self):
        contract = tool_contract("clear_ocular_audio_cache")
        self.assertFalse(contract.read_only)
        self.assertTrue(contract.destructive)
        self.assertTrue(contract.idempotent)

    def test_read_only_tools_are_safe_hints(self):
        contract = tool_contract("search_ocular_audio_video")
        self.assertTrue(contract.read_only)
        self.assertFalse(contract.destructive)
        self.assertTrue(contract.open_world)

    def test_resource_catalog(self):
        resources = resource_catalog()
        self.assertEqual(4, len(resources))
        self.assertEqual(
            {
                "ocularaudio://capabilities",
                "ocularaudio://modes",
                "ocularaudio://health",
                "ocularaudio://contract",
            },
            {item["uri"] for item in resources},
        )

    def test_server_contract_shape(self):
        payload = server_contract("1.3.0", {"capability_modes": {"default": "auto"}}, [{"name": "inspect_video"}])
        self.assertEqual("1.3.0", payload["server"]["version"])
        self.assertEqual("stdio", payload["server"]["transport"])
        self.assertTrue(payload["backward_compatible"]["structured_content"])
        self.assertEqual(["inspect_video"], payload["prompts"])
        self.assertEqual(["stdio", "streamable-http"], payload["transports"])
        self.assertEqual(["sse"], payload["superseded_transports"])


if __name__ == "__main__":
    unittest.main()
