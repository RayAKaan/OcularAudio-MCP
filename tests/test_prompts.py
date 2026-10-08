import unittest

from prompts import (
    PROMPT_NAMES,
    prompt_catalog,
    render_compare_videos,
    render_inspect_video,
    render_search_video_evidence,
    render_visual_review,
)


class PromptTests(unittest.TestCase):
    def test_catalog_is_stable(self):
        catalog = prompt_catalog()
        self.assertEqual(4, len(catalog))
        self.assertEqual(set(PROMPT_NAMES), {item["name"] for item in catalog})

    def test_prompts_are_grounded_templates(self):
        self.assertIn("timestamp", render_inspect_video("https://example.com/v"))
        self.assertIn("Question: refund", render_search_video_evidence("https://example.com/v", "refund"))
        self.assertIn("OCR", render_visual_review("https://example.com/v"))
        self.assertIn("Compare", render_compare_videos("a.json,b.json", "what changed?"))

    def test_required_arguments(self):
        with self.assertRaises(ValueError):
            render_inspect_video("")
        with self.assertRaises(ValueError):
            render_search_video_evidence("url", "")
        with self.assertRaises(ValueError):
            render_compare_videos("", "question")


if __name__ == "__main__":
    unittest.main()
