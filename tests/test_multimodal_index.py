import unittest
from evidence_index import EvidenceSegment
from multimodal_index import (
    MultimodalMoment,
    build_multimodal_moments,
    describe_moment,
    rank_multimodal_moments,
    visual_change_score,
)
from visual_index import VisualFrame


class MultimodalIndexTests(unittest.TestCase):
    def setUp(self):
        self.segment = EvidenceSegment(
            "e1", 10, 20, "Revenue increased after pricing changes",
            score=8.0, chapter="Pricing"
        )
        self.frame1 = VisualFrame(
            "f1", 12, "/tmp/1.jpg", 100, 100, 100, 20, "0" * 64,
            "Revenue 20% increase"
        )
        self.frame2 = VisualFrame(
            "f2", 18, "/tmp/2.jpg", 100, 100, 100, 20, "1" * 64,
            "Pricing chart"
        )

    def test_alignment_creates_multimodal_moments(self):
        moments = build_multimodal_moments([self.segment], [self.frame1, self.frame2])
        self.assertEqual(len(moments), 2)
        self.assertIn("transcript", moments[0].modalities)
        self.assertIn("ocr", moments[0].modalities)

    def test_visual_change_score(self):
        self.assertEqual(visual_change_score(None, self.frame1), 0.0)
        self.assertEqual(visual_change_score(self.frame1, self.frame2), 1.0)

    def test_query_ranking(self):
        moments = build_multimodal_moments([self.segment], [self.frame1, self.frame2])
        results = rank_multimodal_moments(moments, "revenue pricing", top_k=2)
        self.assertEqual(results[0].moment_id, "m00001")

    def test_transcript_only_fallback(self):
        moments = build_multimodal_moments([self.segment], [])
        self.assertEqual(len(moments), 1)
        self.assertEqual(moments[0].modalities, ["transcript"])

    def test_description_marks_change(self):
        moments = build_multimodal_moments([], [self.frame1, self.frame2])
        description = describe_moment(moments[1])
        self.assertEqual(description["visual_signal"], "major_visual_change")


if __name__ == "__main__":
    unittest.main()
