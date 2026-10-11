import asyncio
import json
import sys
import tempfile
import types
import unittest
from pathlib import Path


def _install_lightweight_stubs():
    requests = types.ModuleType("requests")
    requests.Session = type("Session", (), {})
    sys.modules.setdefault("requests", requests)

    yt_api = types.ModuleType("youtube_transcript_api")
    yt_api.YouTubeTranscriptApi = type("YouTubeTranscriptApi", (), {})
    sys.modules.setdefault("youtube_transcript_api", yt_api)

    ytdlp = types.ModuleType("yt_dlp")
    ytdlp.YoutubeDL = type("YoutubeDL", (), {})
    sys.modules.setdefault("yt_dlp", ytdlp)


class MCPV2SurfaceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        _install_lightweight_stubs()
        import ocular_audio_mcp
        cls.server_module = ocular_audio_mcp

    def test_server_identity(self):
        self.assertEqual("OcularAudio Server", self.server_module.mcp.name)
        self.assertEqual("1.3.0", self.server_module.mcp.version)

    def test_hybrid_search_reads_canonical_transcript_cache(self):
        module = self.server_module
        original_cache_dir = module.CACHE_DIR
        url = "https://example.test/pricing-demo.mp4"
        try:
            with tempfile.TemporaryDirectory() as directory:
                module.CACHE_DIR = Path(directory)
                cache_id = module._cache_id(url)
                self.assertTrue(module.write_to_cache(cache_id, {
                    "metadata": {
                        "title": "Pricing demo",
                        "duration": "30s",
                        "chapters": [],
                    },
                    "transcript": (
                        "[00:00] The pricing plans include a starter tier.\n"
                        "[00:10] Enterprise customers receive advanced reporting."
                    ),
                    "method": "test_fixture",
                }))

                result = asyncio.run(module.search_ocular_audio_hybrid(url, "pricing plans"))
                payload = json.loads(result)
                self.assertNotIn("error", payload)
                self.assertGreater(payload["result_count"], 0)
                self.assertIn("pricing", payload["results"][0]["text"].lower())
        finally:
            module.CACHE_DIR = original_cache_dir

    def test_registered_tools_and_resources(self):
        from mcp import Client

        async def check():
            async with Client(self.server_module.mcp) as client:
                tools = await client.list_tools()
                resources = await client.list_resources()
                prompts = await client.list_prompts()
                tool_names = {tool.name for tool in tools.tools}
                resource_uris = {str(resource.uri) for resource in resources.resources}
                prompt_names = {prompt.name for prompt in prompts.prompts}

                self.assertIn("get_ocular_audio_contract", tool_names)
                self.assertEqual(32, len(tool_names))
                self.assertEqual(
                    {
                        "ocularaudio://capabilities",
                        "ocularaudio://modes",
                        "ocularaudio://health",
                        "ocularaudio://contract",
                        "ocularaudio://security",
                        "ocularaudio://readiness",
                        "ocularaudio://metrics",
                    },
                    resource_uris,
                )

                clear_tool = next(
                    tool for tool in tools.tools
                    if tool.name == "clear_ocular_audio_cache"
                )
                self.assertTrue(clear_tool.annotations.destructive_hint)
                self.assertFalse(clear_tool.annotations.read_only_hint)

                prompt_result = await client.get_prompt("search_video_evidence", {"url": "https://example.com/v", "query": "refund"})
                self.assertIn("refund", prompt_result.messages[0].content.text)

                result = await client.call_tool(
                    "get_ocular_audio_contract", {}
                )
                self.assertFalse(result.is_error)
                self.assertIsNotNone(result.structured_content)
                self.assertEqual(
                    "1.0",
                    result.structured_content["contract_version"],
                )

        asyncio.run(check())


if __name__ == "__main__":
    unittest.main()
