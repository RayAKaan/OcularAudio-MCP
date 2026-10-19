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

    def test_modes_resource_exposes_enforceable_budgets(self):
        payload = json.loads(asyncio.run(self.server_module.ocular_audio_modes_resource()))
        self.assertEqual(["lite", "intelligence", "deep", "auto"], payload["available_modes"])
        self.assertEqual(8, payload["policies"]["lite"]["max_evidence"])
        self.assertEqual(24, payload["policies"]["intelligence"]["max_evidence"])
        self.assertEqual(64, payload["policies"]["deep"]["max_evidence"])
        self.assertEqual(32, payload["policies"]["deep"]["max_sources"])
        self.assertIn("capability_gaps", payload["decision_contract"])

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
                manifest_path = Path(directory) / "evidence" / f"{cache_id}.json"
                self.assertTrue(manifest_path.exists())
                manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
                self.assertEqual(1, manifest["schema_version"])
                self.assertTrue(all(item["evidence_id"].startswith("ev_") for item in manifest["records"]))
                self.assertEqual("transcript", payload["results"][0]["source"])
        finally:
            module.CACHE_DIR = original_cache_dir

    def test_query_canonical_evidence_tool_filters_and_returns_provenance(self):
        module = self.server_module
        original_cache_dir = module.CACHE_DIR
        original_visual_cache_dir = module.VISUAL_CACHE_DIR
        url = "https://example.test/canonical-query.mp4"
        try:
            with tempfile.TemporaryDirectory() as directory:
                module.CACHE_DIR = Path(directory)
                module.VISUAL_CACHE_DIR = Path(directory) / "visual"
                module.VISUAL_CACHE_DIR.mkdir(parents=True)
                cache_id = module._cache_id(url)
                self.assertTrue(module.write_to_cache(cache_id, {
                    "metadata": {"title": "Canonical query", "duration": "30s", "chapters": []},
                    "transcript": "[00:02] Revenue increased this quarter.\\n[00:12] Costs remained stable.",
                    "method": "test_fixture",
                }))
                payload = json.loads(asyncio.run(module.query_ocular_audio_evidence(
                    url, modalities=["transcript"], query="revenue", limit=10,
                )))
                self.assertNotIn("error", payload)
                self.assertGreater(payload["result_count"], 0)
                self.assertTrue(all(item["modality"] == "transcript" for item in payload["results"]))
                self.assertTrue(all(item["evidence_id"].startswith("ev_") for item in payload["results"]))
                self.assertTrue(all(item["content_hash"] for item in payload["results"]))
                self.assertTrue(all("provenance" in item for item in payload["results"]))
        finally:
            module.CACHE_DIR = original_cache_dir
            module.VISUAL_CACHE_DIR = original_visual_cache_dir

    def test_visual_only_source_is_persisted_in_canonical_manifest(self):
        module = self.server_module
        original_cache_dir = module.CACHE_DIR
        original_visual_cache_dir = module.VISUAL_CACHE_DIR
        url = "https://example.test/visual-only.mp4"
        try:
            with tempfile.TemporaryDirectory() as directory:
                module.CACHE_DIR = Path(directory)
                module.VISUAL_CACHE_DIR = Path(directory) / "visual"
                module.VISUAL_CACHE_DIR.mkdir(parents=True)
                cache_id = module._cache_id(url)
                module._write_visual_index(cache_id, {
                    "source_id": cache_id, "title": "Visual only", "duration_seconds": 12,
                    "frames": [{
                        "frame_id": "frame-1", "timestamp_seconds": 4,
                        "description": "A dashboard slide", "ocr_text": "Revenue 42",
                        "image_path": "/tmp/frame.jpg",
                    }],
                })
                records = module._refresh_canonical_evidence(cache_id)
                self.assertTrue(records)
                manifest = module._get_evidence_store().read(cache_id)
                self.assertIsNotNone(manifest)
                modalities = {record.modality for record in manifest["records"]}
                self.assertIn("visual", modalities)
                self.assertIn("ocr", modalities)
                self.assertNotIn("transcript", modalities)
        finally:
            module.CACHE_DIR = original_cache_dir
            module.VISUAL_CACHE_DIR = original_visual_cache_dir

    def test_stale_manifest_is_removed_when_source_artifacts_disappear(self):
        module = self.server_module
        original_cache_dir = module.CACHE_DIR
        original_visual_cache_dir = module.VISUAL_CACHE_DIR
        url = "https://example.test/stale-evidence.mp4"
        try:
            with tempfile.TemporaryDirectory() as directory:
                module.CACHE_DIR = Path(directory)
                module.VISUAL_CACHE_DIR = Path(directory) / "visual"
                module.VISUAL_CACHE_DIR.mkdir(parents=True)
                cache_id = module._cache_id(url)
                self.assertTrue(module.write_to_cache(cache_id, {
                    "metadata": {"title": "Temporary source", "duration": "10s", "chapters": []},
                    "transcript": "[00:01] Temporary evidence",
                    "method": "test_fixture",
                }))
                self.assertTrue(module._refresh_canonical_evidence(cache_id))
                self.assertIsNotNone(module._get_evidence_store().read(cache_id))

                (Path(directory) / f"{cache_id}.json").unlink()
                self.assertEqual([], module._refresh_canonical_evidence(cache_id))
                self.assertIsNone(module._get_evidence_store().read(cache_id))
        finally:
            module.CACHE_DIR = original_cache_dir
            module.VISUAL_CACHE_DIR = original_visual_cache_dir

    def test_visual_search_returns_canonical_visual_and_ocr_ids(self):
        module = self.server_module
        original_cache_dir = module.CACHE_DIR
        original_visual_cache_dir = module.VISUAL_CACHE_DIR
        url = "https://example.test/visual-search.mp4"
        try:
            with tempfile.TemporaryDirectory() as directory:
                module.CACHE_DIR = Path(directory)
                module.VISUAL_CACHE_DIR = Path(directory) / "visual"
                module.VISUAL_CACHE_DIR.mkdir(parents=True)
                cache_id = module._cache_id(url)
                module._write_visual_index(cache_id, {
                    "version": module.VISUAL_INDEX_VERSION,
                    "source_id": cache_id, "title": "Revenue slide", "duration_seconds": 12,
                    "frames": [{
                        "frame_id": "frame-revenue", "timestamp_seconds": 4,
                        "image_path": "/tmp/frame.jpg", "width": 640, "height": 360,
                        "brightness": 100, "contrast": 25, "phash": "10101010",
                        "ocr_text": "Revenue increased 42 percent",
                    }],
                })
                payload = json.loads(asyncio.run(module.search_ocular_audio_visuals(
                    url, "revenue", mode="deep",
                )))
                self.assertNotIn("error", payload)
                self.assertEqual(1, payload["result_count"])
                result = payload["results"][0]
                self.assertTrue(result["evidence_id"].startswith("ev_"))
                self.assertTrue(result["ocr_evidence_id"].startswith("ev_"))
                self.assertEqual("frame-revenue", result["provenance"]["frame_id"])
        finally:
            module.CACHE_DIR = original_cache_dir
            module.VISUAL_CACHE_DIR = original_visual_cache_dir

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
                self.assertIn("query_ocular_audio_evidence", tool_names)
                self.assertEqual(33, len(tool_names))
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
