import os
import tempfile
import unittest

import cv2
import numpy as np

from visual_index import (
    VisualFrame,
    frame_descriptor,
    hamming_distance,
    normalize_crop_box,
    sample_timestamps,
    search_visual_frames,
    select_burst_timestamps,
)


class VisualIndexTests(unittest.TestCase):
    def test_sampling_and_burst_are_bounded(self):
        self.assertEqual(sample_timestamps(25, interval_seconds=10), [0, 10, 20, 25])
        self.assertEqual(select_burst_timestamps(20, radius_seconds=4, count=5), [16, 18, 20, 22, 24])

    def test_crop_normalization(self):
        self.assertEqual(
            normalize_crop_box(0.25, 0.25, 0.5, 0.5, 1000, 800),
            (250, 200, 750, 600),
        )
        self.assertEqual(
            normalize_crop_box(-10, -10, 5000, 5000, 1000, 800, normalized=False),
            (0, 0, 1000, 800),
        )

    def test_descriptor_and_phash(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "frame.jpg")
            image = np.zeros((100, 160, 3), dtype=np.uint8)
            image[:, :80] = 255
            cv2.imwrite(path, image)
            frame = frame_descriptor(path, 12, "f00001", "Revenue $100")
            self.assertEqual(frame.width, 160)
            self.assertEqual(frame.height, 100)
            self.assertEqual(len(frame.phash), 64)
            self.assertGreater(frame.contrast, 0)
            self.assertEqual(hamming_distance(frame.phash, frame.phash), 0)

    def test_visual_search(self):
        frames = [
            VisualFrame("f1", 10, "/tmp/1.jpg", 100, 100, 10, 5, "0" * 64, "Revenue grew by 20%"),
            VisualFrame("f2", 20, "/tmp/2.jpg", 100, 100, 10, 5, "1" * 64, "A product demo"),
        ]
        results = search_visual_frames(frames, "revenue 20%", top_k=2)
        self.assertEqual(results[0].frame_id, "f1")
        self.assertGreater(results[0].score, results[1].score)

    def test_empty_search(self):
        self.assertEqual(search_visual_frames([], "anything"), [])
        self.assertEqual(search_visual_frames([], ""), [])


if __name__ == "__main__":
    unittest.main()
