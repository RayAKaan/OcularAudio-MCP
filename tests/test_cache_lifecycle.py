import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import ocular_audio_mcp as server


class CacheLifecycleTests(unittest.TestCase):
    def test_clear_all_removes_batch_results_and_nested_frame_artifacts(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            visual = root / "visual"
            frames = visual / "frames"
            batches = root / "batches"
            evidence = root / "evidence"
            for path in (visual, frames, batches, evidence):
                path.mkdir(parents=True, exist_ok=True)
            (root / "video.json").write_text("{}", encoding="utf-8")
            (visual / "video.json").write_text("{}", encoding="utf-8")
            (evidence / "video.json").write_text("{}", encoding="utf-8")
            (batches / "batch.json").write_text("{}", encoding="utf-8")
            frame_dir = frames / "video"
            frame_dir.mkdir()
            (frame_dir / "frame.jpg").write_bytes(b"frame")

            with patch.object(server, "CACHE_DIR", root), patch.object(server, "VISUAL_CACHE_DIR", visual), patch.object(server, "VISUAL_FRAME_DIR", frames), patch.object(server, "BATCH_CACHE_DIR", batches):
                result = server._clear_cache()

            self.assertGreaterEqual(result["cleared"], 5)
            self.assertFalse((root / "video.json").exists())
            self.assertFalse((visual / "video.json").exists())
            self.assertFalse((evidence / "video.json").exists())
            self.assertFalse((batches / "batch.json").exists())
            self.assertFalse(frame_dir.exists())

    def test_clear_one_source_invalidates_dependent_batch_result(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            visual = root / "visual"
            frames = visual / "frames"
            batches = root / "batches"
            for path in (visual, frames, batches, root / "evidence"):
                path.mkdir(parents=True, exist_ok=True)
            batch_path = batches / "batch.json"
            batch_path.write_text(json.dumps({
                "sources": [{
                    "source": {
                        "source_id": "stable-source-id",
                        "url": "https://www.youtube.com/watch?v=video123",
                    }
                }]
            }), encoding="utf-8")

            with patch.object(server, "CACHE_DIR", root), patch.object(server, "VISUAL_CACHE_DIR", visual), patch.object(server, "VISUAL_FRAME_DIR", frames), patch.object(server, "BATCH_CACHE_DIR", batches), patch.object(server, "_get_evidence_store", return_value=type("Store", (), {"delete": lambda self, source_id: False})()):
                result = server._clear_cache("video123")

            self.assertEqual(1, result["cleared"])
            self.assertFalse(batch_path.exists())


if __name__ == "__main__":
    unittest.main()
