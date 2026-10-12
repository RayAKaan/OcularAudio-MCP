import unittest

from capability_modes import (
    MODE_POLICIES, build_mode_decision, get_mode_policy, is_feature_allowed,
    mode_capabilities, mode_execution_controls, mode_output_contract,
    normalize_mode, resolve_mode,
)


class CapabilityModeTests(unittest.TestCase):
    def test_modes_and_aliases(self):
        self.assertEqual(normalize_mode("light"), "lite")
        self.assertEqual(normalize_mode("smart"), "intelligence")
        self.assertEqual(normalize_mode("extreme"), "deep")

    def test_explicit_modes(self):
        self.assertEqual(resolve_mode("lite", "analyze this"), "lite")
        self.assertEqual(resolve_mode("intelligence", "anything"), "intelligence")
        self.assertEqual(resolve_mode("deep", "anything"), "deep")

    def test_auto_escalation(self):
        self.assertEqual(resolve_mode("auto", "what is this video about?"), "lite")
        self.assertEqual(resolve_mode("auto", "find every occurrence of pricing"), "deep")
        self.assertEqual(resolve_mode("auto", "find the pricing chart"), "intelligence")

    def test_policy_depth_and_limits(self):
        self.assertEqual(set(MODE_POLICIES), {"lite", "intelligence", "deep"})
        lite, intel, deep = (get_mode_policy(name) for name in ("lite", "intelligence", "deep"))
        self.assertLess(lite.max_evidence, intel.max_evidence)
        self.assertLess(intel.max_evidence, deep.max_evidence)
        self.assertLess(lite.max_frames, intel.max_frames)
        self.assertLess(intel.max_frames, deep.max_frames)
        self.assertEqual(lite.analysis_depth, "glance")
        self.assertEqual(deep.analysis_depth, "omniscient")
        self.assertFalse(lite.ocr)
        self.assertTrue(deep.ocr)

    def test_shared_contract_and_serializable_decision(self):
        capabilities = mode_capabilities()
        self.assertTrue(capabilities["shared_source_coverage"])
        self.assertTrue(capabilities["single_package"])
        self.assertTrue(capabilities["single_local_mcp"])
        contract = mode_output_contract("deep")
        self.assertEqual(contract["resolved_mode"], "deep")
        self.assertEqual(contract["mode_decision"]["limits"]["max_frames"], 64)

    def test_auto_uses_source_count_features_duration_and_budget(self):
        self.assertEqual(resolve_mode("auto", source_count=14), "deep")
        self.assertEqual(resolve_mode("auto", requested_features=["multimodal"]), "intelligence")
        self.assertEqual(resolve_mode("auto", budget_seconds=20), "lite")
        self.assertEqual(resolve_mode("auto", estimated_duration_seconds=7200), "intelligence")

    def test_runtime_capabilities_report_gaps(self):
        decision = build_mode_decision(
            "deep", requested_features=["ocr", "visual"],
            available_capabilities={"opencv": False, "ffmpeg": False, "tesseract": False},
        ).to_dict()
        self.assertFalse(decision["features"]["visual"])
        self.assertFalse(decision["features"]["multimodal"])
        self.assertFalse(decision["features"]["ocr"])
        self.assertEqual(3, len(decision["capability_gaps"]))
        self.assertTrue(decision["adjustments"])

    def test_execution_controls_enforce_mode_budgets(self):
        lite = mode_execution_controls("lite", top_k=50, interval_seconds=1, enable_ocr=True)
        self.assertEqual(8, lite["top_k"])
        self.assertEqual(15, lite["interval_seconds"])
        self.assertFalse(lite["enable_ocr"])
        deep = mode_execution_controls("deep", top_k=100, interval_seconds=None)
        self.assertEqual(64, deep["top_k"])
        self.assertEqual(3, deep["interval_seconds"])
        self.assertEqual(64, deep["decision"]["limits"]["max_frames"])

    def test_feature_allowlist_is_fail_closed(self):
        self.assertFalse(is_feature_allowed("lite", "ocr"))
        self.assertTrue(is_feature_allowed("deep", "ocr"))
        self.assertFalse(is_feature_allowed("deep", "not_a_feature"))

    def test_invalid_inputs_are_rejected(self):
        for kwargs in (
            {"source_count": 0}, {"source_count": 33},
            {"budget_seconds": 0}, {"estimated_duration_seconds": -1},
        ):
            with self.subTest(kwargs=kwargs), self.assertRaises(ValueError):
                build_mode_decision("auto", **kwargs)
        with self.assertRaises(ValueError):
            mode_execution_controls("lite", interval_seconds=0)


if __name__ == "__main__":
    unittest.main()
