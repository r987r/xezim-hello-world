"""Negative checks for the passive connected-memory evidence validator.

Synthetic strings here ONLY exercise rejection logic; they are not simulation
artifacts and never qualify RTL or appear as a successful regression.
"""
import unittest
from unittest.mock import patch

from tools import pcie_connected_roundtrip_evidence as evidence


def fixture():
    plan = "f" * 64
    return "\n".join([
        f"PCIE_RC_BAR_MWR_TX: action=write_bar0 addr=80001100 data=a5c36e91 plan={plan}",
        "PCIE_CONNECTED_SRAM_DATA_OK: addr=0000000012000100 data=00000000a5c36e91 strb=0f",
        "PCIE_CONNECTED_SRAM_WRITE: actual_host_mwr=1 real_bridge=1 generated_noc=1 real_sram_write=1 addr=0000000012000100 beats=4",
        "PCIE_RC_BAR_MRD_TX: action=write_bar0 addr=80001100 tag=7",
        "PCIE_CONNECTED_SRAM_READ: real_sram_read=1 addr=0000000012000100",
        "PCIE_CONNECTED_EP_TX_CPLD: returned_completion=1 from_actual_sram=1",
        "PCIE_RC_BAR_MRD_RX: tag=7 status=0 bytes=4 data=a5c36e91",
        "PCIE_RC_BAR_MRD_CPLD_PASS: addr=80001100 data=a5c36e91 same_real_host=1",
        f"PCIE_SCN_DRIVER: plan={plan} action=write_bar0 stage=driver_done",
    ])


class ConnectedRoundtripEvidenceTests(unittest.TestCase):
    def assess(self, text, *, qualified_bar=True):
        # This mocks ONLY the independently unit-tested BAR config validator,
        # never an actual original host simulation or qualification job.
        with patch.object(evidence, "bar_check",
                          return_value={"qualified_over_link_bar0": qualified_bar}):
            return evidence.check(text)

    def test_structural_fixture_for_negative_mutations_only(self):
        record = self.assess(fixture())
        self.assertTrue(record["qualified_connected_memory_roundtrip"])
        self.assertEqual(record["scope"].split(";")[-1], "not_cpu_boot")

    def test_missing_duplicate_out_of_order_or_corrupted_observations_fail(self):
        source = fixture()
        lines = source.splitlines()
        for index in range(len(lines)):
            with self.subTest(missing=index):
                self.assertFalse(self.assess("\n".join(lines[:index]+lines[index+1:]))[
                    "qualified_connected_memory_roundtrip"])
        with self.subTest("duplicate"):
            self.assertFalse(self.assess(source+"\n"+lines[1])[
                "qualified_connected_memory_roundtrip"])
        with self.subTest("out-of-order"):
            swapped = lines.copy()
            swapped[3],swapped[4]=swapped[4],swapped[3]
            self.assertFalse(self.assess("\n".join(swapped))[
                "qualified_connected_memory_roundtrip"])
        for before,after in (
            ("a5c36e91 strb=0f", "a5c36e90 strb=0f"),
            ("bytes=4 data=a5c36e91", "bytes=4 data=a5c36e90"),
            ("tag=7 status=0", "tag=8 status=0"),
            ("actual_host_mwr=1", "actual_host_mwr=0"),
            ("real_sram_read=1", "real_sram_read=0"),
            ("same_real_host=1", "same_real_host=0"),
            ("beats=4", "beats=3"),
            ("0000000012000100", "0000000012000104"),
        ):
            with self.subTest(change=before):
                self.assertFalse(self.assess(source.replace(before,after))[
                    "qualified_connected_memory_roundtrip"])

    def test_bar0_original_host_validation_is_not_optional(self):
        self.assertFalse(self.assess(fixture(),qualified_bar=False)[
            "qualified_connected_memory_roundtrip"])


if __name__=="__main__":
    unittest.main()
