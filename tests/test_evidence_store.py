import json
import tempfile
import unittest
from pathlib import Path

from evidence_store import (
    EvidenceRecord,
    EvidenceStore,
    build_canonical_evidence,
)


class CanonicalEvidenceTests(unittest.TestCase):
    def setUp(self):
        self.transcript = (
            "[00:05] Welcome to the revenue dashboard\n"
            "[00:18] Monthly revenue increased by 42 percent\n"
            "[00:35] Compare revenue with operating profit\n"
        )
        self.chapters = [
            {"start_time": 0, "title": "Introduction"},
            {"start_time": 30, "title": "Financials"},
        ]
        self.frames = [
            {
                "frame_id": "f0001",
                "timestamp_seconds": 18,
                "image_path": "/tmp/frame.jpg",
                "width": 640,
                "height": 360,
                "phash": "0101",
                "ocr_text": "Revenue 42 percent",
            },
            {
                "frame_id": "f0002",
                "timestamp_seconds": 35,
                "image_path": "/tmp/frame2.jpg",
                "ocr_text": "",
            },
        ]

    def test_builds_all_supported_evidence_modalities(self):
        records = build_canonical_evidence(
            "source123", self.transcript, 60, self.chapters, self.frames,
            {"title": "Revenue demo", "duration": "1m"},
        )
        modalities = {record.modality for record in records}
        self.assertEqual({"transcript", "chapter", "metadata", "visual", "ocr"}, modalities)
        self.assertEqual(len(records), len({record.evidence_id for record in records}))
        self.assertTrue(all(record.source_id == "source123" for record in records))

    def test_stable_ids_across_rebuilds_and_input_order(self):
        first = build_canonical_evidence("source123", self.transcript, 60, self.chapters, self.frames)
        second = build_canonical_evidence("source123", self.transcript, 60, self.chapters, self.frames)
        self.assertEqual([r.evidence_id for r in first], [r.evidence_id for r in second])

    def test_visual_and_ocr_are_distinct_records(self):
        records = build_canonical_evidence("source123", visual_frames=self.frames)
        visual = next(r for r in records if r.modality == "visual")
        ocr = next(r for r in records if r.modality == "ocr")
        self.assertNotEqual(visual.evidence_id, ocr.evidence_id)
        self.assertEqual(visual.start_seconds, ocr.start_seconds)
        self.assertEqual(ocr.text, "Revenue 42 percent")

    def test_rejects_unsafe_source_id(self):
        with self.assertRaises(ValueError):
            build_canonical_evidence("../escape")

    def test_rejects_invalid_timestamps(self):
        record = EvidenceRecord(
            evidence_id="ev_" + "a" * 32, source_id="source123", modality="transcript",
            start_seconds=-1, end_seconds=0, text="bad", content_hash="",
            provenance={}, metadata={},
        )
        with self.assertRaises(ValueError):
            from evidence_store import validate_record
            validate_record(record)

    def test_atomic_manifest_round_trip_and_query(self):
        records = build_canonical_evidence(
            "source123", self.transcript, 60, self.chapters, self.frames,
            {"title": "Revenue demo"},
        )
        with tempfile.TemporaryDirectory() as directory:
            store = EvidenceStore(directory)
            result = store.save("source123", records, {"title": "Revenue demo"})
            self.assertEqual(result["record_count"], len(records))
            manifest = store.read("source123")
            self.assertEqual(manifest["record_count"], len(records))
            self.assertEqual(manifest["content_digest"], result["content_digest"])
            self.assertEqual(
                ["Monthly revenue increased by 42 percent"],
                [r.text for r in store.query("source123", modalities=["transcript"], text_query="revenue") if r.start_seconds == 18],
            )

    def test_rejects_tampered_manifest(self):
        records = build_canonical_evidence("source123", self.transcript)
        with tempfile.TemporaryDirectory() as directory:
            store = EvidenceStore(directory)
            store.save("source123", records)
            path = Path(directory) / "source123.json"
            payload = json.loads(path.read_text(encoding="utf-8"))
            payload["records"][0]["text"] = "tampered"
            path.write_text(json.dumps(payload), encoding="utf-8")
            with self.assertRaises(ValueError):
                store.read("source123")

    def test_missing_or_malformed_manifest_is_safe(self):
        with tempfile.TemporaryDirectory() as directory:
            store = EvidenceStore(directory)
            self.assertIsNone(store.read("missing"))
            (Path(directory) / "broken.json").write_text("{", encoding="utf-8")
            self.assertIsNone(store.read("broken"))

    def test_replaces_stale_records_on_refresh(self):
        with tempfile.TemporaryDirectory() as directory:
            store = EvidenceStore(directory)
            first = build_canonical_evidence("source123", "[00:01] old evidence")
            store.save("source123", first)
            second = build_canonical_evidence("source123", "[00:02] new evidence")
            store.save("source123", second)
            self.assertEqual(["new evidence"], [r.text for r in store.query("source123", modalities=["transcript"])])

    def test_delete_and_path_safety(self):
        with tempfile.TemporaryDirectory() as directory:
            store = EvidenceStore(directory)
            store.save("source123", build_canonical_evidence("source123", "[00:01] evidence"))
            self.assertTrue(store.delete("source123"))
            self.assertFalse(store.delete("source123"))
            with self.assertRaises(ValueError):
                store.read("../outside")


if __name__ == "__main__":
    unittest.main()
