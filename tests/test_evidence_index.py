import unittest

from evidence_index import (
    build_evidence_segments,
    format_timestamp,
    nearest_evidence,
    parse_timestamped_transcript,
    search_evidence,
    timeline_window,
)


class EvidenceIndexTests(unittest.TestCase):
    TRANSCRIPT = (
        "[00:05] Welcome to the revenue dashboard\n"
        "[00:18] The monthly revenue increased by 42 percent\n"
        "[00:35] Now compare revenue with operating profit\n"
        "[01:10] The final chart shows customer retention\n"
    )

    def test_parse_timestamped_transcript(self):
        parsed = parse_timestamped_transcript(self.TRANSCRIPT)
        self.assertEqual(parsed[0], (5, "Welcome to the revenue dashboard"))
        self.assertEqual(parsed[1][0], 18)

    def test_build_segments_and_chapters(self):
        segments = build_evidence_segments(
            self.TRANSCRIPT,
            duration_seconds=100,
            chapters=["[00:00] Introduction", "[00:30] Financials"],
        )
        self.assertEqual(len(segments), 4)
        self.assertEqual(segments[1].chapter, "Introduction")
        self.assertEqual(segments[2].chapter, "Financials")
        self.assertEqual(segments[0].end_seconds, 18)

    def test_search_prefers_exact_and_relevant_evidence(self):
        segments = build_evidence_segments(self.TRANSCRIPT)
        results = search_evidence(segments, "monthly revenue increased", top_k=3)
        self.assertEqual(results[0].start_seconds, 18)
        self.assertGreater(results[0].score, results[1].score)

    def test_timeline_and_nearest(self):
        segments = build_evidence_segments(self.TRANSCRIPT)
        window = timeline_window(segments, 30, 40)
        self.assertEqual([item.start_seconds for item in window], [18, 35])
        self.assertEqual(nearest_evidence(segments, 34).start_seconds, 35)

    def test_format_timestamp(self):
        self.assertEqual(format_timestamp(5), "[00:05]")
        self.assertEqual(format_timestamp(3665), "[01:01:05]")


if __name__ == "__main__":
    unittest.main()
