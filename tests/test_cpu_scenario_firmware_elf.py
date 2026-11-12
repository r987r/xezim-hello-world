"""Fast real RV32I compiler/linker gate for source-selected SCN-C CPU firmware.

The existing full-chip preflight previously linked only the default CPU app;
the first typed SCN-C scenario then failed after costly RTL regeneration due
to an unavailable libc header. This test links the actual opt-in scenario C
image in -nostdlib mode for two different source-selected replay seeds.
It asserts *compilation and selection parity only*, not completed RTL/DMA.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import shutil
import tempfile
import unittest

import yaml

from dv.common.scenario import canonical_json
from tools.cpu_dma_firmware import compile_firmware

ROOT = Path(__file__).resolve().parents[1]


class SelectedCpuScenarioFirmwareTests(unittest.TestCase):
    def test_two_source_selected_scenarios_link_as_real_freestanding_rv32i(self):
        missing = [tool for tool in ("clang", "llvm-objcopy", "ld.lld")
                   if shutil.which(tool) is None]
        if missing:
            # Broad check-config/make dv suites intentionally do not install
            # LLVM. Skip ONLY their optional discovery; the dedicated
            # scenario-cpu-elf workflow requires a real cross-toolchain
            # and fails closed if any executable is missing.
            if os.environ.get("SOC_REQUIRE_SCENARIO_RV32I_TOOLS") == "1":
                self.fail("SCN-C RV32I required compiler tools unavailable: " +
                          ", ".join(missing))
            self.skipTest("SCN-C real RV32I toolchain unavailable in general "
                          "unit suite; dedicated scenario-cpu-elf is required: " +
                          ", ".join(missing))
        cfg = yaml.safe_load((ROOT / "config/soc.yaml").read_text())
        with tempfile.TemporaryDirectory(prefix="cpu-scn-real-elf-") as scratch:
            selected = []
            for seed in (79, 80):
                out = Path(scratch) / f"seed-{seed}"
                result = compile_firmware(cfg, out, scenario_mode=True,
                                          scenario_seed=seed)
                plan_raw = (out / "scenario-plan.json").read_bytes()
                plan = json.loads(plan_raw)
                self.assertEqual(plan_raw, canonical_json(plan).encode("ascii"))
                self.assertEqual(plan["seed"], seed)
                expected_sha = hashlib.sha256(plan_raw).hexdigest()
                action_header = (out / "soc_scenario_contract.h").read_text()
                physical_header = (out / "scenario_dma_contract.h").read_text()
                contract = json.loads((out / "scenario-contract.json").read_text())
                self.assertIn(f'#define SOC_SCN_PLAN_SHA256 "{expected_sha}"',
                              action_header)
                self.assertEqual(contract["plan_sha256"], expected_sha)
                self.assertIn("#define SOC_SCN_ACTION_COUNT 8", action_header)
                self.assertIn("SOC_SCN_ACTION_TRACE_PHYS", physical_header)
                self.assertIn("SOC_SCN_PLAN_SHA_WORD_7", physical_header)
                self.assertEqual(contract["action_trace_bytes"], 64)
                self.assertEqual(contract["action_trace_phys"],
                                 contract["plan_witness_phys"] + 32)
                elf = (out / "cpu_dma.elf").read_bytes()
                binary = (out / "cpu_dma.bin").read_bytes()
                self.assertEqual(elf[:6], bytes((0x7f, 0x45, 0x4c, 0x46, 1, 1)))
                self.assertTrue(binary)
                self.assertEqual(binary, result["data"])
                self.assertEqual(hashlib.sha256(binary).hexdigest(),
                                 result["sha256"])
                selected.append((expected_sha, result["sha256"]))
            self.assertNotEqual(selected[0][0], selected[1][0],
                                "different scenario seeds must select different plans")
            self.assertNotEqual(selected[0][1], selected[1][1],
                                "real linked CPU image did not contain selected source digest")


if __name__ == "__main__":
    unittest.main()
