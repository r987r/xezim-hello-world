"""Canonical naming is derived from the same configured regression source."""
from __future__ import annotations

import copy
from pathlib import Path
import sys
import tempfile
import unittest

import yaml

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"tools"))
from test_identity import (
    IdentityError,catalog,config_target,load,relative_path,save,selected,simulator,
)


class IdentityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tests=yaml.safe_load((ROOT/"config/regression.yaml").read_text())["tests"]

    def test_all_registered_targets_have_vendor_neutral_logical_identity(self):
        keys=catalog(self.tests)
        self.assertEqual(len(keys),len(self.tests))
        self.assertEqual(len(self.tests),29)
        for (_,_,logical),target in keys.items():
            for vendor in ("floonoc","litedram","peakrdl","picorv32","pulp","serv","verilog-axi"):
                self.assertNotIn(vendor,logical,(target,logical))
        a=self.tests["chip-cpu-scenario"]
        b=self.tests["chip-dma-scenario"]
        self.assertEqual(a["logical_test"],b["logical_test"])
        self.assertNotEqual(config_target(a),config_target(b))
        self.assertEqual(simulator(a),"verilator")
        self.assertEqual(simulator(self.tests["noc-verilator"]),"verilator")
        self.assertEqual(simulator(self.tests["noc-xezim"]),"xezim")

    def test_config_changes_keep_logical_test_but_change_identity(self):
        a=self.tests["boot"]
        b=self.tests["boot-relocated"]
        self.assertEqual(a["logical_test"],b["logical_test"])
        self.assertNotEqual(config_target(a),config_target(b))
        self.assertEqual(self.tests["sram"]["logical_test"],
                         self.tests["sram-synthesis"]["logical_test"])
        self.assertNotEqual(config_target(self.tests["sram"]),
                            config_target(self.tests["sram-synthesis"]))

    def test_selected_digest_path_run_nonce_and_legacy_target(self):
        with tempfile.TemporaryDirectory() as temp:
            plan=copy.deepcopy(self.tests["chip-cpu-scenario"])
            p=selected("chip-cpu-scenario",plan,env={})
            q=selected("chip-cpu-scenario",plan,env={})
            self.assertNotEqual(p["run_id"],q["run_id"])
            self.assertEqual(p["config_sha256"],q["config_sha256"])
            self.assertEqual(relative_path(p).parts[:3],
                             ("verilator","soc-cpu-dma-scenario","dma-sram-ddr-roundtrip"))
            path=Path(temp)/"identity.json"
            save(path,p)
            self.assertEqual(load(path,target="chip-cpu-scenario",plan=plan),p)
            self.assertIn("local-",relative_path(p).as_posix())
            with self.assertRaisesRegex(IdentityError,"foreign"):
                load(path,target="chip-dma-scenario")
            changed=copy.deepcopy(p)
            changed["testname"]="edited-test"
            import json
            path.write_text(json.dumps(changed))
            with self.assertRaisesRegex(IdentityError,"digest mismatch"):
                load(path)

    def test_ci_run_provenance_and_failed_duplicate_registry(self):
        plan=self.tests["memory"]
        p=selected("memory",plan,env={"GITHUB_RUN_ID":"123","GITHUB_RUN_ATTEMPT":"2"})
        self.assertRegex(p["run_id"],r"^ci-123-a2-[a-f0-9]{12}$")
        with self.assertRaisesRegex(IdentityError,"invalid CI"):
            selected("memory",plan,env={"GITHUB_RUN_ID":".."})
        bad=copy.deepcopy(self.tests)
        bad["memory-false-duplicate"]=copy.deepcopy(bad["memory"])
        with self.assertRaisesRegex(IdentityError,"duplicate canonical identity"):
            catalog(bad)
        bad=self.tests.copy()
        bad["memory"]={**bad["memory"],"logical_test":"other_vendor/read"}
        with self.assertRaisesRegex(IdentityError,"lowercase"):
            catalog(bad)

    def test_dependency_and_interface_changes_alter_config_provenance(self):
        from test_identity import SOURCE_LOCKS, OPTIONAL_SOURCE_LOCKS
        plan=self.tests["chip-cpu-scenario"]
        baseline=selected("chip-cpu-scenario",plan,run_id="local-012345abcdef")
        self.assertIn("source_lock_sha256",baseline["selection"])
        locks=baseline["selection"]["source_lock_sha256"]
        self.assertEqual(set(locks),set(SOURCE_LOCKS)|set(OPTIONAL_SOURCE_LOCKS))
        self.assertTrue(locks["config/interface_contracts.yaml"])
        self.assertTrue(locks["config/ip.lock.yaml"])
        import hashlib
        for path in SOURCE_LOCKS:
            self.assertEqual(locks[path],hashlib.sha256((ROOT/path).read_bytes()).hexdigest())
        drift=copy.deepcopy(baseline)
        drift["selection"]["source_lock_sha256"]["config/ip.lock.yaml"]="0"*64
        from test_identity import validate
        with self.assertRaisesRegex(IdentityError,"fingerprint mismatch"):
            validate(drift)

    def test_selected_plan_must_match_exact_selected_configuration(self):
        from test_identity import validate
        plan=copy.deepcopy(self.tests["chip-cpu-scenario"])
        identity=selected("chip-cpu-scenario",plan,run_id="local-012345abcdef")
        validate(identity,target="chip-cpu-scenario",plan=plan)
        for key,altered in (("firmware_mode","alternate-firmware"),
                            ("bender_targets",["different"]),
                            ("memory_config","config/examples/memory-fabric-sparse.yaml"),
                            ("top","foreign_top")):
            modified=copy.deepcopy(plan)
            modified[key]=altered
            with self.subTest(key=key), self.assertRaises(IdentityError):
                validate(identity,target="chip-cpu-scenario",plan=modified)

    def test_no_unchecked_path_or_engine_aliases(self):
        plan=self.tests["memory"]
        with self.assertRaisesRegex(IdentityError,"invalid execution ID"):
            selected("memory",plan,run_id="../oops")
        with self.assertRaisesRegex(IdentityError,"unsupported simulator"):
            simulator({**plan,"engine":"unknown-simulator"})


if __name__=="__main__":
    unittest.main()
