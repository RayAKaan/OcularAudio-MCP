import asyncio
import json
import tempfile
import unittest
from pathlib import Path

from batch_index import (
    BatchItem,
    BatchSource,
    compare_batch_results,
    parse_batch_manifest,
    rank_cross_video_results,
    read_batch_result,
    run_batch,
    stable_batch_id,
    stable_batch_source_id,
    summarize_batch,
    validate_concurrency,
    write_batch_result,
)


class BatchIndexTests(unittest.TestCase):
    def test_manifest_parsing_deduplicates_sources(self):
        sources = parse_batch_manifest(json.dumps([
            "https://example.com/a",
            {"url": "https://example.com/a", "label": "duplicate"},
            {"url": "https://example.com/b", "label": "B"},
        ]))
        self.assertEqual(2, len(sources))
        self.assertEqual("B", sources[1].label)

    def test_manifest_accepts_object(self):
        sources = parse_batch_manifest(json.dumps({"videos": [{"url": "https://example.com/a"}]}))
        self.assertEqual(1, len(sources))

    def test_manifest_rejects_too_many_sources(self):
        manifest = json.dumps([f"https://example.com/{i}" for i in range(33)])
        with self.assertRaises(ValueError):
            parse_batch_manifest(manifest)

    def test_ids_are_stable(self):
        self.assertEqual(
            stable_batch_source_id(" https://example.com/a "),
            stable_batch_source_id("https://example.com/a"),
        )
        sources = parse_batch_manifest('["https://example.com/a","https://example.com/b"]')
        self.assertEqual(stable_batch_id(sources), stable_batch_id(sources))

    def test_concurrency_bounds(self):
        self.assertEqual(1, validate_concurrency(1))
        self.assertEqual(4, validate_concurrency(4))
        with self.assertRaises(ValueError):
            validate_concurrency(5)

    def test_run_batch_isolates_failures(self):
        async def worker(source):
            if source.label == "bad":
                raise RuntimeError("boom")
            await asyncio.sleep(0)
            return {"results": [{"modalities": ["transcript"]}]}

        sources = [
            BatchSource("a", "a", "good"),
            BatchSource("b", "b", "bad"),
            BatchSource("c", "c", "good"),
        ]
        items = asyncio.run(run_batch(sources, worker, max_concurrency=2))
        self.assertEqual(["success", "error", "success"], [item.status for item in items])
        self.assertEqual("boom", items[1].error)

    def test_cross_video_ranking(self):
        items = [
            BatchItem(
                BatchSource("a", "a", "Video A"),
                "success",
                {"results": [{"timestamp_seconds": 10, "transcript": [{"text": "pricing plans"}], "ocr_text": "", "evidence_score": 0.8, "visual_change_score": 0.0, "modalities": ["transcript"]}]},
            ),
            BatchItem(
                BatchSource("b", "b", "Video B"),
                "success",
                {"results": [{"timestamp_seconds": 20, "transcript": [{"text": "unrelated"}], "ocr_text": "pricing", "evidence_score": 0.2, "visual_change_score": 0.1, "modalities": ["visual", "ocr"]}]},
            ),
        ]
        ranked = rank_cross_video_results(items, "pricing")
        self.assertEqual("a", ranked[0]["source_id"])
        self.assertEqual(2, len(ranked))

    def test_comparison_scorecard(self):
        items = [
            BatchItem(BatchSource("a", "a", "A"), "success", {"results": [{"transcript": [{"text": "pricing"}], "ocr_text": "", "evidence_score": 1.0, "visual_change_score": 0.0}]}),
            BatchItem(BatchSource("b", "b", "B"), "error", error="unavailable"),
        ]
        rows = compare_batch_results(items, "pricing")
        self.assertEqual("a", rows[0]["source_id"])
        self.assertEqual("error", rows[1]["status"])

    def test_summary_counts(self):
        items = [
            BatchItem(BatchSource("a", "a"), "success", {"results": [{"modalities": ["transcript", "visual"]}]}),
            BatchItem(BatchSource("b", "b"), "error", error="x"),
        ]
        summary = summarize_batch(items)
        self.assertEqual(2, summary["source_count"])
        self.assertEqual(1, summary["success_count"])
        self.assertEqual(1, summary["error_count"])
        self.assertFalse(summary["complete"])

    def test_atomic_persistence(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)
            write_batch_result(path, "abc", {"status": "complete"})
            self.assertEqual({"status": "complete"}, read_batch_result(path, "abc"))


if __name__ == "__main__":
    unittest.main()
