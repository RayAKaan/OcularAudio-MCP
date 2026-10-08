import unittest
from capability_modes import get_mode_policy, mode_capabilities, mode_output_contract, normalize_mode, resolve_mode

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

    def test_policy_depth(self):
        lite = get_mode_policy("lite")
        intel = get_mode_policy("intelligence")
        deep = get_mode_policy("deep")
        self.assertLess(lite.max_evidence, intel.max_evidence)
        self.assertLess(intel.max_evidence, deep.max_evidence)
        self.assertEqual(lite.analysis_depth, "glance")
        self.assertEqual(deep.analysis_depth, "omniscient")
        self.assertFalse(lite.ocr)
        self.assertTrue(deep.ocr)

    def test_shared_contract(self):
        capabilities = mode_capabilities()
        self.assertTrue(capabilities["shared_source_coverage"])
        self.assertTrue(capabilities["single_package"])
        self.assertTrue(capabilities["single_local_mcp"])
        self.assertEqual(mode_output_contract("deep")["resolved_mode"], "deep")

if __name__ == "__main__":
    unittest.main()
