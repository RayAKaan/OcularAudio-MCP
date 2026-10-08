import tempfile
import unittest
from pathlib import Path

from media_resolver import (
    SUPPORTED_ANALYSIS_LEVELS,
    analysis_policy,
    classify_source,
    detect_platform,
    normalize_analysis_level,
    stable_source_id,
)


class MediaResolverTests(unittest.TestCase):
    def test_analysis_levels_and_aliases(self):
        self.assertEqual(normalize_analysis_level("minimal"), "glance")
        self.assertEqual(normalize_analysis_level("standard"), "understand")
        self.assertEqual(normalize_analysis_level("deep"), "deep")
        self.assertEqual(normalize_analysis_level("extreme"), "omniscient")
        self.assertEqual(set(SUPPORTED_ANALYSIS_LEVELS), {"glance", "understand", "deep", "omniscient"})

    def test_policy_escalates_without_aliasing(self):
        self.assertFalse(analysis_policy("glance")["ocr"])
        self.assertTrue(analysis_policy("understand")["ocr"])
        self.assertEqual(analysis_policy("omniscient")["frame_strategy"], "maximum")
        self.assertTrue(analysis_policy("omniscient")["preserve_raw"])

    def test_platform_detection(self):
        self.assertEqual(detect_platform("https://www.youtube.com/watch?v=abc"), "youtube")
        self.assertEqual(detect_platform("https://www.tiktok.com/@x/video/1"), "tiktok")
        self.assertEqual(detect_platform("https://example.com/video.mp4"), "generic_web")
        self.assertEqual(detect_platform("https://example.com/video", "Vimeo"), "vimeo")
        self.assertEqual(detect_platform("https://www.snapchat.com/spotlight/1"), "snapchat")

    def test_local_source_classification(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "sample.mp4"
            path.write_bytes(b"not-a-real-video")
            result = classify_source(str(path))
            self.assertEqual(result["source_kind"], "local_file")
            self.assertEqual(result["media_type"], "video")
            self.assertTrue(result["exists"])

    def test_source_ids_are_stable(self):
        self.assertEqual(
            stable_source_id("https://www.youtube.com/watch?v=dQw4w9WgXcQ"),
            "dQw4w9WgXcQ",
        )
        self.assertEqual(
            stable_source_id("https://example.com/a.mp4"),
            stable_source_id("https://example.com/a.mp4"),
        )


if __name__ == "__main__":
    unittest.main()
