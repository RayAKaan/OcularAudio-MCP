import asyncio
import tempfile
import unittest
from pathlib import Path

from agentic_index import (
    AuditRecord,
    ExecutionPolicy,
    append_audit_record,
    build_execution_plan,
    classify_intent,
    execute_with_policy,
    health_report,
    normalize_query,
    read_audit_records,
)


class AgenticIndexTests(unittest.TestCase):
    def test_intent_classification(self):
        self.assertEqual("search_video", classify_intent("find pricing"))
        self.assertEqual("inspect_visual", classify_intent("show the chart"))
        self.assertEqual("timeline", classify_intent("when did they discuss pricing"))
        self.assertEqual("inspect_ocr", classify_intent("read the text on screen"))
        self.assertEqual("compare_videos", classify_intent("compare these", multi_video=True))

    def test_query_limit(self):
        with self.assertRaises(ValueError):
            normalize_query("x" * 1001)

    def test_plan_is_stable_and_bounded(self):
        plan_a = build_execution_plan("find revenue")
        plan_b = build_execution_plan("find revenue")
        self.assertEqual(plan_a.plan_id, plan_b.plan_id)
        self.assertLessEqual(len(plan_a.steps), 8)
        self.assertEqual("search_hybrid", plan_a.steps[0].operation)

    def test_policy_validation(self):
        self.assertEqual(2, ExecutionPolicy(max_retries=2).validate().max_retries)
        with self.assertRaises(ValueError):
            ExecutionPolicy(timeout_seconds=0).validate()
        with self.assertRaises(ValueError):
            ExecutionPolicy(max_retries=4).validate()

    def test_execute_retries_and_records_success(self):
        state = {"attempts": 0}

        async def worker():
            state["attempts"] += 1
            if state["attempts"] == 1:
                raise RuntimeError("transient")
            return {"ok": True}

        result, audit = asyncio.run(execute_with_policy(
            "test", worker, ExecutionPolicy(max_retries=1, backoff_seconds=0)
        ))
        self.assertEqual({"ok": True}, result)
        self.assertEqual(2, state["attempts"])
        self.assertEqual("success", audit.status)

    def test_execute_timeout(self):
        async def worker():
            await asyncio.sleep(0.02)
            return {"ok": True}

        result, audit = asyncio.run(execute_with_policy(
            "timeout", worker, ExecutionPolicy(timeout_seconds=0.005, max_retries=0)
        ))
        self.assertIsNone(result)
        self.assertEqual("error", audit.status)

    def test_health_report(self):
        report = health_report(
            {"ffmpeg": True, "opencv": True, "whisper": {"available": True}, "tesseract": {"available": True}},
            cache_dir=Path(tempfile.gettempdir()),
            batch_cache_dir=Path(tempfile.gettempdir()),
        )
        self.assertEqual("healthy", report["status"])

    def test_audit_roundtrip(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "audit.jsonl"
            append_audit_record(path, AuditRecord(1.0, "x", "success", 2.0, {"a": 1}))
            self.assertEqual(1, len(read_audit_records(path)))
            self.assertEqual("success", read_audit_records(path)[0]["status"])


if __name__ == "__main__":
    unittest.main()
