import json
import shutil
import subprocess
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CLI = ROOT / "bin" / "cli.js"


@unittest.skipUnless(shutil.which("node") and shutil.which("python3"), "Node.js and Python 3 are required")
class CLIMCPStdioTests(unittest.TestCase):
    def test_bare_cli_invocation_performs_mcp_initialize(self):
        request = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {
                "protocolVersion": "2025-06-18",
                "capabilities": {},
                "clientInfo": {"name": "ocularaudio-ci", "version": "1.0.0"},
            },
        }
        completed = subprocess.run(
            ["node", str(CLI)],
            input=json.dumps(request) + "\n",
            capture_output=True,
            text=True,
            cwd=ROOT,
            timeout=20,
        )
        self.assertEqual(completed.returncode, 0, msg=completed.stderr[-4000:])
        protocol_lines = [line for line in completed.stdout.splitlines() if line.strip()]
        self.assertTrue(protocol_lines, msg=f"No MCP response. stderr: {completed.stderr[-4000:]}")
        response = json.loads(protocol_lines[0])
        self.assertEqual("2.0", response.get("jsonrpc"))
        self.assertEqual(1, response.get("id"))
        self.assertEqual("OcularAudio Server", response["result"]["serverInfo"]["name"])
        self.assertEqual("1.3.0", response["result"]["serverInfo"]["version"])


    def test_stdio_round_trip_lists_tools_and_calls_a_real_tool(self):
        messages = [
            {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "initialize",
                "params": {
                    "protocolVersion": "2025-06-18",
                    "capabilities": {},
                    "clientInfo": {"name": "ocularaudio-e2e", "version": "1.0.0"},
                },
            },
            {"jsonrpc": "2.0", "method": "notifications/initialized"},
            {"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}},
            {
                "jsonrpc": "2.0",
                "id": 3,
                "method": "tools/call",
                "params": {"name": "get_ocular_audio_contract", "arguments": {}},
            },
        ]
        completed = subprocess.run(
            ["node", str(CLI)],
            input="".join(json.dumps(message) + "\\n" for message in messages),
            capture_output=True,
            text=True,
            cwd=ROOT,
            timeout=30,
        )
        self.assertEqual(0, completed.returncode, msg=completed.stderr[-4000:])
        responses = {}
        for line in completed.stdout.splitlines():
            if not line.strip():
                continue
            payload = json.loads(line)
            if "id" in payload:
                responses[payload["id"]] = payload

        self.assertEqual({1, 2, 3}, set(responses), msg=completed.stdout[-8000:])
        initialized = responses[1]["result"]
        self.assertEqual("OcularAudio Server", initialized["serverInfo"]["name"])

        listed_tools = responses[2]["result"]["tools"]
        tool_names = {tool["name"] for tool in listed_tools}
        self.assertEqual(33, len(tool_names))
        self.assertIn("get_ocular_audio_contract", tool_names)
        self.assertIn("query_ocular_audio_evidence", tool_names)

        tool_result = responses[3]["result"]
        self.assertFalse(tool_result.get("isError", False))
        self.assertTrue(tool_result.get("content"), msg=tool_result)
        rendered = json.dumps(tool_result, ensure_ascii=False)
        self.assertIn("contract_version", rendered)


if __name__ == "__main__":
    unittest.main()
