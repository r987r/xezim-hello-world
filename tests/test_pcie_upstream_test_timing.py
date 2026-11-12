"""Original upstream timing override is test-only, version-pinned and reversible."""
import unittest

from tools.pcie_upstream_test_timing import (
    patched, CORE_BEFORE, CORE_AFTER, TEST_BEFORE, TEST_AFTER,
    ENUM_BEFORE, ENUM_AFTER,
)


class UpstreamTimingOverlayTests(unittest.TestCase):
    def test_fusesoc_sim_target_only_receives_fast_override(self):
        source="CAPI=2:\nname: original\n"+CORE_BEFORE+"\n  verilate:\n    flow: sim\n"
        got=patched("pcie_phy.core",source)
        self.assertIn(CORE_AFTER,got)
        self.assertEqual(got.count("-GSIM_FAST_LINK=1"),1)
        self.assertIn("  verilate:\n    flow: sim",got)
        self.assertIn("  sim:\n    flow: sim",got)

    def test_original_pyuvm_timeout_extended_without_faking_link(self):
        source="async def run_phase(self):\n    "+TEST_BEFORE+"\n"
        result=patched("verif/tests/test_pcie_core.py",source)
        self.assertIn(TEST_AFTER,result)
        self.assertNotIn(TEST_BEFORE,result)
        self.assertNotIn("force",result)

    def test_upstream_memory_stall_probe_is_passive_and_rethrows(self):
        source = "async def body(self):\n" + ENUM_BEFORE + "\n"
        got = patched("verif/sequences/pcie_enumeration_seq.py", source)
        self.assertIn(ENUM_AFTER, got)
        self.assertIn("PCIE_UPSTREAM_MEM_STALL", got)
        self.assertIn("raise", got)
        self.assertNotIn("force", got)
        self.assertNotIn("send(", got)
        self.assertNotIn("write(", got)

    def test_source_drift_and_repeat_fail_closed(self):
        for path,source in (("pcie_phy.core","wrong content"),
                            ("verif/tests/test_pcie_core.py","wrong content"),
                            ("verif/sequences/pcie_enumeration_seq.py","wrong content")):
            with self.subTest(path=path),self.assertRaisesRegex(ValueError,"changed"):
                patched(path,source)
        with self.assertRaisesRegex(ValueError,"changed"):
            patched("pcie_phy.core",CORE_BEFORE+CORE_BEFORE)
        with self.assertRaisesRegex(ValueError,"unknown"):
            patched("incorrect.core",CORE_BEFORE)


if __name__=="__main__":
    unittest.main()
