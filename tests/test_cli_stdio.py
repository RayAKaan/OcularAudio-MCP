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


if __name__ == "__main__":
    unittest.main()
