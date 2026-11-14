"""SCN-2 source-neutral compiled C / real BFM boundary contract tests."""
from __future__ import annotations

import copy
import json
from pathlib import Path
import shutil
import sys
import subprocess
import tempfile
import unittest

import yaml

from dv.common.scenario import ScenarioError, canonical_json, resolve_scenario
from dv.common.scenario_dma import EXAMPLE, compile_contract, load_contract_from_plan, materialize, render_c_header

ROOT = Path(__file__).resolve().parents[1]


class ScenarioDmaTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.cfg = yaml.safe_load((ROOT / "config/soc.yaml").read_text())

    def setUp(self):
        self.spec = json.loads((ROOT / EXAMPLE).read_text())
        self.plan = resolve_scenario(self.spec, self.cfg)

    def test_identical_contract_for_cpu_and_bfm(self):
        c = compile_contract(self.plan)
        self.assertEqual(c["scenario_id"], "cpu_bfm_ddr_roundtrip")
        self.assertEqual(c["source_phys"], 0x10002000)
        self.assertEqual(c["return_phys"], 0x10002040)
        self.assertEqual(c["ddr_phys"], 0x140000100)
        self.assertEqual(c["length"], 64)
        self.assertEqual(c["seed"], 90)
        self.assertEqual(c["execution_state"], "pending_real_rtl")
        self.assertEqual(c["plan_witness_phys"], 0x10003000)
        self.assertEqual(c["action_trace_phys"], 0x10003020)
        self.assertEqual(c["action_trace_bytes"], 64)
        emitted = render_c_header(c)
        self.assertIn("#define SOC_SCN_ACTION_TRACE_PHYS 0x10003020ULL", emitted)
        self.assertIn("#define SOC_SCN_PLAN_WITNESS_PHYS 0x10003000ULL", emitted)
        sha_bytes = bytes.fromhex(c["plan_sha256"])
        for idx in range(8):
            word = int.from_bytes(sha_bytes[idx*4:idx*4+4], "little")
            self.assertIn(
                f"#define SOC_SCN_PLAN_SHA_WORD_{idx} 0x{word:08x}u", emitted)
        self.assertIn("#define SOC_SCN_DDR_PHYS 0x140000100ULL", render_c_header(c))
        self.assertIsNone(self.plan["execution_evidence"])

    def test_shared_random_payload_replays_identically_for_real_cpu_and_bfm(self):
        baseline = compile_contract(self.plan)
        self.assertEqual(baseline["seed"], 90)
        with tempfile.TemporaryDirectory() as tmp:
            a, ca = materialize(self.cfg, Path(tmp)/"cpu", scenario_seed=79)
            b, cb = materialize(self.cfg, Path(tmp)/"bfm", scenario_seed=79)
            self.assertEqual(ca, cb)
            self.assertEqual(ca["plan_sha256"], cb["plan_sha256"])
            self.assertEqual(ca["seed"], 90)
            self.assertEqual(a["seed"], 79)
            self.assertEqual(a, b)
            alternate, alt_contract = materialize(self.cfg, Path(tmp)/"alternative",
                                                  scenario_seed=80)
            self.assertEqual(alternate["seed"], 80)
            self.assertEqual(alt_contract["seed"], 91)
            self.assertNotEqual(alt_contract["plan_sha256"], ca["plan_sha256"])
            self.assertNotEqual(alt_contract["seed"], ca["seed"])
            self.assertEqual(compile_contract(alternate), alt_contract)
            for bad in (-1, 2**32, True, "79"):
                with self.subTest(seed=bad), self.assertRaisesRegex(
                        ScenarioError, "uint32"):
                    materialize(self.cfg, Path(tmp)/"bad", scenario_seed=bad)

    def test_shared_random_group_rejects_unequal_pattern_domains(self):
        mismatched = copy.deepcopy(self.spec)
        checked = next(a for a in mismatched["actions"]
                       if a["action_instance_id"] == "check_return")
        checked["args"]["pattern"]["seed"]["randint"]["max"] = 92
        with self.assertRaisesRegex(ScenarioError, "incompatible bounds"):
            resolve_scenario(mismatched, self.cfg)

    def test_materializes_same_bytes_and_c_head_after_repeat(self):
        with tempfile.TemporaryDirectory() as temp:
            out = Path(temp)
            plan, c = materialize(self.cfg, out)
            original = (out / "scenario-plan.json").read_bytes()
            contract = (out / "scenario-contract.json").read_bytes()
            header = (out / "scenario_dma_contract.h").read_bytes()
            action_table = (out / "soc_scenario_contract.h").read_bytes()
            self.assertIn(b"#define SOC_SCN_ACTION_COUNT 8", action_table)
            self.assertIn(c["plan_sha256"].encode("ascii"), action_table)
            self.assertEqual(original, canonical_json(self.plan).encode("ascii"))
            self.assertEqual(c, load_contract_from_plan(out / "scenario-plan.json"))
            materialize(self.cfg, out)
            self.assertEqual((out / "scenario-plan.json").read_bytes(), original)
            self.assertEqual((out / "scenario-contract.json").read_bytes(), contract)
            self.assertEqual((out / "scenario_dma_contract.h").read_bytes(), header)
            self.assertEqual((out / "soc_scenario_contract.h").read_bytes(), action_table)

    def test_check_origin_requires_causal_init_and_same_pattern(self):
        for field, bad in (("expected_from", "ddr"), ("pattern", {"kind": "constant", "seed": 91})):
            with self.subTest(field=field):
                scenario = copy.deepcopy(self.spec)
                target = next(a for a in scenario["actions"]
                              if a["action_instance_id"] == "check_return")
                target["args"][field] = bad
                with self.assertRaises(ScenarioError):
                    compile_contract(resolve_scenario(scenario, self.cfg))

    def test_compiler_rejects_unsupported_action_rewrite(self):
        for field, bad in (("length", 128), ("dst", "src")):
            with self.subTest(field=field):
                malformed = copy.deepcopy(self.plan)
                target = next(a for a in malformed["actions"]
                              if a["action_instance_id"] == "copy_back")
                target["args"][field] = bad
                with self.assertRaises(ScenarioError):
                    compile_contract(malformed)

    def test_rejects_proof_manufactured_in_intent(self):
        forged = copy.deepcopy(self.plan)
        forged["execution_evidence"] = {"result": "pass"}
        with self.assertRaisesRegex(ScenarioError, "intent"):
            compile_contract(forged)

    def test_freestanding_scenario_compiles_in_host_c_syntax_checker(self):
        compiler = shutil.which("cc") or shutil.which("clang")
        if not compiler:
            self.skipTest("host C compiler unavailable")
        with tempfile.TemporaryDirectory() as temp:
            out = Path(temp)
            materialize(self.cfg, out)
            mapping = {r["name"]: int(r["base"], 0)
                       for space in ("data", "config")
                       for r in self.cfg["address_map"][space]}
            flags = {
                "SOC_CPU0_SRAM": mapping["compute0.sram"],
                "SOC_DDR_BASE": mapping["memory0.ddr0"],
                "SOC_DMA0_CSR": mapping["compute0.dma"],
                "SOC_MAILBOX": mapping["compute0.sram"] + 0x400,
                "SOC_MODEL_BYTES": 1 << self.cfg["verification"]["memory"]["model_address_bits"],
            }
            cmd = [compiler, "-std=c11", "-Wall", "-Wextra", "-Werror",
                   "-fsyntax-only", "-I", str(out),
                   *[f"-D{k}=0x{v:x}ULL" for k, v in flags.items()],
                   str(ROOT / "sw/dma/tests/scenario_dma_run.c")]
            subprocess.run(cmd, check=True, cwd=ROOT, capture_output=True, text=True)

    def test_regression_targets_opt_in_and_share_scenario(self):
        # regress.py is also a CLI and imports sibling tools by bare name.
        # Mirror the established tests/test_regression.py sys.path setup.
        if str(ROOT / 'tools') not in sys.path:
            sys.path.insert(0, str(ROOT / 'tools'))
        from tools.regress import expand, load_config
        config = load_config(ROOT / "config/regression.yaml")
        self.assertEqual(expand(config, ["scenario"]),
                         ["chip-cpu-scenario", "chip-dma-scenario"])
        self.assertEqual(config["tests"]["chip-cpu-scenario"]["firmware_mode"], "cpu_dma_scenario")
        self.assertEqual(config["tests"]["chip-dma-scenario"]["firmware_mode"], "scenario_bfm")
        self.assertNotIn("SOC_SCENARIO_PLAN", config["tests"]["chip-dma"]["env"])
        self.assertEqual(config["tests"]["chip-cpu-dma"]["firmware_mode"], "cpu_dma")


if __name__ == "__main__":
    unittest.main()
