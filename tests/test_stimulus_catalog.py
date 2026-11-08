"""Fail-closed human-authored YAML stimulus coverage, provenance and behavior."""
from __future__ import annotations

import copy
from pathlib import Path
import shutil
from tempfile import TemporaryDirectory
import unittest
import yaml

from tools.stimulus_catalog import load, StimulusCatalogError, SOURCE

ROOT=Path(__file__).resolve().parents[1]


class StimulusCatalogTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.config=yaml.safe_load((ROOT/"config/regression.yaml").read_text())

    def test_all_registered_targets_and_single_shared_cpu_bfm_scenario(self):
        entries=load(self.config)
        self.assertEqual(len(entries),len(self.config['tests']))
        self.assertEqual(entries["chip-cpu-scenario"]["sha256"],
                         entries["chip-dma-scenario"]["sha256"])
        self.assertEqual(entries["chip-cpu-scenario"]["scenario_source"],
                         "config/scenarios/cpu-bfm-ddr-roundtrip.json")
        self.assertEqual(entries["smoke"]["execution"],"legacy_opaque")
        self.assertIsNone(entries["smoke"]["driver_source"])
        self.assertEqual(entries["smoke"]["rtl_top"],"hello_world_tb")
        self.assertEqual(entries["chip-ethernet-cpu"]["driver_source"],
                         "dv/ethernet0/test_cpu_mvp.py")
        self.assertEqual(entries["supernoc"]["driver_source"],
                         "dv/supernoc/test_supernoc.py")
        self.assertEqual(entries["supernoc-latency"]["driver_source"],
                         "dv/supernoc/test_latency.py")
        self.assertEqual(entries["noc-verilator"]["execution"],"non_runtime")
        self.assertFalse(entries["noc-verilator"]["phases"]["run"])

    def test_unlisted_new_target_and_deleted_existing_target_fail(self):
        bad=copy.deepcopy(self.config)
        bad["tests"]["brand-new-test"]=copy.deepcopy(bad["tests"]["smoke"])
        with self.assertRaisesRegex(StimulusCatalogError,"coverage mismatch"):
            load(bad)
        bad=copy.deepcopy(self.config)
        del bad["tests"]["smoke"]
        with self.assertRaisesRegex(StimulusCatalogError,"unknown configured target"):
            load(bad)

    def test_mismatched_adapter_or_executable_scenario_fail(self):
        bad=copy.deepcopy(self.config)
        bad["tests"]["smoke"]["firmware_mode"]="scenario_bfm"
        with self.assertRaisesRegex(StimulusCatalogError,"execution differs"):
            load(bad)
        bad=copy.deepcopy(self.config)
        bad["tests"]["chip-dma-scenario"]["flow_plan"]="config/scenarios/another.json"
        with self.assertRaisesRegex(StimulusCatalogError,"scenario source differs"):
            load(bad)

    def test_unknown_source_and_duplicate_yaml_keys_fail(self):
        with TemporaryDirectory() as tmp:
            root=Path(tmp)
            loc=root/SOURCE
            loc.parent.mkdir(parents=True)
            # The fixture intentionally excludes real RTL execution, but the
            # source catalog also requires every selected driver's path to
            # exist. Materialize only path placeholders, not fake RTL results.
            for test in self.config["tests"].values():
                module=test.get("module")
                if module:
                    driver=root/(test.get("test_dir") or ".")/(module.replace(".","/")+".py")
                    driver.parent.mkdir(parents=True, exist_ok=True)
                    driver.touch()
            source=(ROOT/SOURCE).read_text()
            # A second declaration must never silently replace the first one.
            loc.write_text(source.replace("schema_version: 1",
                                          "schema_version: 1\\nschema_version: 1".replace("\\n","\n"),1))
            with self.assertRaisesRegex(StimulusCatalogError,"duplicate"):
                load(self.config,root=root)
            loc.write_text(source.replace("config/scenarios/cpu-bfm-ddr-roundtrip.json",
                                          "config/scenarios/nonexistent.json"))
            with self.assertRaisesRegex(StimulusCatalogError,"unsafe/absent executable"):
                load(self.config,root=root)

    def test_declared_phase_descriptions_do_not_become_executed_stimulus(self):
        from tools.test_intent import catalog
        intents=catalog(self.config)
        opaque=intents["smoke"]
        self.assertEqual(opaque["declared_actions"],0)
        self.assertEqual(opaque["execution_adoption"],"legacy_runtime_without_action_contract")
        self.assertFalse(opaque["evidence_required_for_display"])
        self.assertEqual(len(opaque["stimulus_outline"]["run"]),1)
        self.assertNotIn("passed",opaque)


if __name__=="__main__":
    unittest.main()
