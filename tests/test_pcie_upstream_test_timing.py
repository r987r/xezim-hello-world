"""Original upstream timing override is test-only, version-pinned and reversible."""
import unittest

from tools.pcie_upstream_test_timing import (
    patched, CORE_BEFORE, CORE_AFTER, TEST_BEFORE, TEST_AFTER,
    ENUM_BEFORE, ENUM_AFTER, ENUM_MODEL_BEFORE, ENUM_MODEL_AFTER,
    ENUM_HOST_BEFORE, ENUM_HOST_AFTER,
    ENUM_READ_BEFORE, ENUM_READ_AFTER, ENUM_EP_CPL_BEFORE, ENUM_EP_CPL_AFTER,
    ENUM_RC_FC_BEFORE, ENUM_RC_FC_AFTER, ENUM_HOST_FC_BEFORE, ENUM_HOST_FC_AFTER,
    CPLD_READY_REL, CPLD_READY_BEFORE, CPLD_READY_AFTER, CPLD_ROUNDING,
    PIPE_MONITOR_SOURCE, PIPE_MONITOR_TLP_BEFORE, PIPE_MONITOR_TLP_AFTER,
    PIPE_MONITOR_DLLP_BEFORE, PIPE_MONITOR_DLLP_AFTER,
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
        source = ("async def body(self):\n" + ENUM_MODEL_BEFORE + "\n" +
                  ENUM_BEFORE + "\n" + ENUM_RC_FC_BEFORE + "\n" +
                  ENUM_HOST_FC_BEFORE + "\n" + ENUM_HOST_BEFORE + "\n" +
                  ENUM_READ_BEFORE + "\n" + ENUM_EP_CPL_BEFORE + "\n")
        got = patched("verif/sequences/pcie_enumeration_seq.py", source)
        self.assertIn(ENUM_AFTER, got)
        self.assertIn(ENUM_MODEL_AFTER, got)
        self.assertIn(ENUM_HOST_AFTER, got)
        self.assertIn("PCIE_UPSTREAM_RC_FC_PROFILE", got)
        self.assertIn("PCIE_UPSTREAM_RC_UPDATEFC_CPL_TX", got)
        self.assertIn("PCIE_UPSTREAM_RC_UPDATEFC_CPL_DONE", got)
        self.assertIn("host_port.fc_update_steps = cocotb.utils.get_sim_steps(1, 'us')", got)
        self.assertIn("assert host_port.fc_update_steps == original_fc_steps", got)
        self.assertNotIn("tx_credit_limit =", got)
        self.assertNotIn("rx_credits_allocated =", got)
        self.assertNotIn("tx_credits_consumed =", got)
        self.assertIn("PCIE_UPSTREAM_RC_TX_BEGIN", got)
        self.assertIn("PCIE_UPSTREAM_RC_TX_DONE", got)
        self.assertIn("PCIE_UPSTREAM_MEM_STALL", got)
        self.assertIn("PCIE_UPSTREAM_FC_SNAPSHOT", got)
        self.assertIn("PCIE_UPSTREAM_READBACK_TIMEOUT", got)
        self.assertIn("PCIE_UPSTREAM_READBACK_FC", got)
        self.assertIn("PCIE_UPSTREAM_READBACK_RC", got)
        self.assertIn("PCIE_UPSTREAM_READBACK_RTL_SNAPSHOT", got)
        self.assertIn("cplh_credit_limit_r", got)
        self.assertIn("cpld_credits_consumed_r", got)
        self.assertIn("not_exposed", got)
        self.assertIn("PCIE_UPSTREAM_EP_CPL_BEGIN", got)
        self.assertIn("PCIE_UPSTREAM_EP_CPL_DRIVER_DONE", got)
        self.assertIn("assert readback == test_data", got)
        self.assertIn("tx_credits_available", got)
        self.assertIn("tx_credits_consumed", got)
        self.assertIn("rx_credits_allocated", got)
        self.assertNotIn("tx_consume_fc(", got)
        self.assertNotIn("tx_credit_limit =", got)
        self.assertIn("raise", got)
        self.assertNotIn("force", got)
        self.assertNotIn("send(", got)
        self.assertNotIn("write(", got)

    def test_reuse_original_openpcie_pipe_tlp_dllp_decoder_callbacks(self):
        source = ("class pipe_monitor:\n" +
                  PIPE_MONITOR_TLP_BEFORE + "\n" +
                  PIPE_MONITOR_DLLP_BEFORE + "\n")
        got = patched(PIPE_MONITOR_SOURCE, source)
        self.assertIn(PIPE_MONITOR_TLP_AFTER, got)
        self.assertIn(PIPE_MONITOR_DLLP_AFTER, got)
        self.assertIn("PCIE_UPSTREAM_PIPE_MON_TLP: direction=EP_TO_RC", got)
        self.assertIn("PCIE_UPSTREAM_PIPE_MON_DLLP: direction=EP_TO_RC", got)
        self.assertIn("self.pipe_agent_config.tlp_received.append(tlp)", got)
        self.assertIn("self.pipe_agent_config.dllp_received.append(dllp)", got)
        self.assertNotIn("self.pipe_agent_config.tlp_received.clear()", got)
        self.assertNotIn("self.pipe_agent_config.dllp_received.clear()", got)
        with self.assertRaisesRegex(ValueError, "changed"):
            patched(PIPE_MONITOR_SOURCE, got)
        with self.assertRaisesRegex(ValueError, "changed"):
            patched(PIPE_MONITOR_SOURCE, source.replace(
                PIPE_MONITOR_TLP_BEFORE, "def altered_monitor(self):"))
        with self.assertRaisesRegex(ValueError, "changed"):
            patched(PIPE_MONITOR_SOURCE, source.replace(
                PIPE_MONITOR_DLLP_BEFORE, ""))

    def test_updatefc_host_profile_is_pinned_and_non_bypassing(self):
        sample = ("class sequence:\n" + ENUM_RC_FC_BEFORE + "\n" +
                  ENUM_HOST_FC_BEFORE + "\n")
        # Both source-locked transforms must reject unrelated provider changes.
        with self.assertRaisesRegex(ValueError, "changed"):
            from tools.pcie_upstream_test_timing import replace_once
            replace_once(sample, "nonexistent pinned anchor", "foo", "test")
        self.assertIn("fc_update_steps", ENUM_RC_FC_AFTER)
        self.assertIn("DllpType.UPDATE_FC_CPL", ENUM_HOST_FC_AFTER)
        self.assertIn("await self.finish_item", ENUM_HOST_FC_AFTER)
        self.assertNotIn("rx_release_fc(", ENUM_RC_FC_AFTER)
        self.assertNotIn("tx_consume_fc(", ENUM_RC_FC_AFTER)
        self.assertNotIn("dut.", ENUM_RC_FC_AFTER)

    def test_original_cpld_first_beat_waits_for_valid_and_ready(self):
        source = ("module tlp2dllp;\n"
                  + CPLD_ROUNDING + "\n" + CPLD_ROUNDING + "\n"
                  + "dllp_valid_o            = '0;\n"
                  + CPLD_READY_BEFORE + "\nendmodule\n")
        got = patched(CPLD_READY_REL, source)
        self.assertEqual(got.count(CPLD_READY_AFTER), 1)
        self.assertIn("PCIE_UPSTREAM_CPLD_CREDIT_STALL", got)
        self.assertEqual(got.count("PCIE_UPSTREAM_CPLD_CREDIT_STALL"), 1)
        self.assertIn("cplh_credit_limit_r", got)
        self.assertIn("cpld_credits_consumed_r", got)
        self.assertIn("if (rst_i || curr_state != ST_CHECK_CREDITS_CPLH_CPLD", got)
        self.assertNotIn(CPLD_READY_BEFORE + "\n", got)
        # These are source checks, not a fabricated upstream PASS.
        self.assertEqual(got.count(CPLD_ROUNDING), 2)
        self.assertIn("dllp_valid_o            = '0;", got)
        self.assertNotIn("dllp_valid_o            = '1;", got)
        with self.assertRaisesRegex(ValueError, "changed"):
            patched(CPLD_READY_REL, got)
        with self.assertRaisesRegex(ValueError, "changed"):
            patched(CPLD_READY_REL, source.replace(CPLD_ROUNDING, "tampered"))
        # This negative fixture must fail specifically at the disabled
        # experimental retry guard, not only at a generic source mismatch.
        with self.assertRaisesRegex(ValueError, "experimental retry-enable drift"):
            patched(CPLD_READY_REL, source.replace(
                "dllp_valid_o            = '0;",
                "dllp_valid_o            = '1;"))

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
