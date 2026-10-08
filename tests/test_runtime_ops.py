import json
from pathlib import Path
import tempfile
import unittest

from runtime_ops import (
    MetricsRegistry,
    OperationTimer,
    ReadinessCheck,
    build_readiness,
    rotate_audit_log,
    validate_retention,
)


class RuntimeOpsTests(unittest.TestCase):
    def test_metrics_are_bounded_and_aggregated(self):
        metrics = MetricsRegistry(max_keys=2)
        metrics.increment("requests")
        metrics.increment("requests", 2)
        metrics.observe("requests", 10)
        metrics.observe("requests", 20)
        snapshot = metrics.snapshot()
        self.assertEqual(3, snapshot["counters"]["requests"])
        self.assertEqual(15.0, snapshot["durations"]["requests"]["avg_ms"])

    def test_operation_timer_records_success(self):
        metrics = MetricsRegistry()
        timer = OperationTimer(metrics, "demo")
        timer.finish("success")
        snapshot = metrics.snapshot()
        self.assertEqual(1, snapshot["counters"]["operations.demo.success"])

    def test_readiness_contract(self):
        result = build_readiness(
            checks=[ReadinessCheck("cache", True), ReadinessCheck("ffmpeg", False, "missing")],
            version="1.3.0",
            metrics=MetricsRegistry(),
        )
        self.assertEqual("not_ready", result["status"])
        self.assertFalse(result["checks"][1]["ready"])

    def test_audit_rotation_preserves_active_log(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "audit.jsonl"
            path.write_text(json.dumps({"event": "x"}) + "\n" * 100, encoding="utf-8")
            rotated = rotate_audit_log(path, max_bytes=1024, max_files=3)
            self.assertTrue(path.exists())
            self.assertTrue(rotated)
            self.assertTrue(path.with_name("audit.jsonl.1").exists())

    def test_retention_validation(self):
        self.assertEqual((2048, 3), validate_retention(2048, 3))
        with self.assertRaises(ValueError):
            validate_retention(512, 3)
        with self.assertRaises(ValueError):
            validate_retention(2048, 21)


if __name__ == "__main__":
    unittest.main()
