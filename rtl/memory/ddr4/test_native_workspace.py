"""Standalone DDR run packaging contracts (no simulator or RTL stimulus)."""
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from dfi_to_protocol import convert, standalone_plan, TARGET
from run_functional import CORE_NAME, TEST_CASE, verify_native_execution
import test_dfi_to_protocol
from tools.run_workspace import reserve_run
from tools.test_identity import relative_path, selected


class DDRNativeWorkspaceTests(unittest.TestCase):
    def test_preserve_original_xml_and_reject_failed_or_foreign_invocation(self):
        with tempfile.TemporaryDirectory() as temp:
            out = Path(temp)
            build = out / "scratch"
            build.mkdir()
            control, source = out / "keep.vlt", out / "top.v"
            command = {"simulator": "verilator", "global_public_flat_rw": False,
                       "argv": ["verilator", "-Mdir", str(build), "--top-module", CORE_NAME,
                                "--vpi", str(control), str(source)]}
            (out / "ddr4_compiler_command.json").write_text(json.dumps(command))
            xunit = build / "somerun_results.xml"
            test = f'<testcase classname="functional_tb" name="{TEST_CASE}">'
            clean = f"<testsuites>{test}</testcase></testsuites>".encode()
            xunit.write_bytes(f"<testsuites>{test}<failure /></testcase></testsuites>".encode())
            with self.assertRaisesRegex(ValueError, "did not pass"):
                verify_native_execution(build, out, [source], control)
            self.assertFalse((out / "results.xml").exists())
            xunit.write_bytes(clean)
            with self.assertRaisesRegex(ValueError, "compiler invocation"):
                verify_native_execution(build, out, [out / "foreign.v"], control)
            verify_native_execution(build, out, [source], control)
            self.assertEqual((out / "results.xml").read_bytes(), clean)

    def test_canonical_converter_is_bound_to_native_selection(self):
        with tempfile.TemporaryDirectory() as temp:
            plan = standalone_plan(CORE_NAME)
            files = b"/existing/generated/ddr4.v\n"
            env = {"GITHUB_RUN_ID": "321", "GITHUB_RUN_ATTEMPT": "2"}
            identity = selected(TARGET, plan, filelist_bytes=files, env=env)
            workspace = reserve_run(Path(temp) / "runs", identity, plan=plan)
            plan_file = workspace / "plan.json"
            plan_file.write_text(json.dumps({**plan, "identity": identity}))
            (workspace / "sources.f").write_bytes(files)
            test_dfi_to_protocol.DDRUnifiedProtocolTests().inputs(workspace)
            source = {"commit": "a" * 40, "dirty": False,
                      "workflow_run_id": "321", "workflow_attempt": "2"}
            native = {"status": "pass", "top": CORE_NAME, "source": source,
                      "identity_sha256": identity["identity_sha256"]}
            native_file = workspace / "ddr4_functional_result.json"
            native_file.write_text(json.dumps({**native, "identity_sha256": "foreign"}))
            with self.assertRaisesRegex(ValueError, "differs from selected run"):
                convert(workspace, workspace, identity=identity)
            self.assertFalse((workspace / "result.json").exists())
            native_file.write_text(json.dumps(native))
            mrs_file = workspace / "ddr4_mrs_evidence.json"
            mrs_original = b'{"fixture":true}\n'
            mrs_file.write_bytes(mrs_original)
            before = plan_file.read_bytes()
            # DFI samples above are test fixtures. The genuine MRS scoreboard
            # and Git-source introspection are separate production gates.
            with patch("protocol_report.subprocess.check_output",
                       side_effect=["a" * 40, ""]), patch("ddr_mr_report.read_evidence") as validate:
                with patch.dict(os.environ, env):
                    convert(workspace, workspace, identity=identity)
            validate.assert_called_once_with(mrs_file, workspace / "protocol-transactions.json")
            result = json.loads((workspace / "result.json").read_text())
            self.assertEqual(result["canonical_id"], relative_path(identity).as_posix())
            self.assertEqual(result["identity_sha256"], identity["identity_sha256"])
            self.assertEqual(mrs_file.read_bytes(), mrs_original)
            self.assertEqual(plan_file.read_bytes(), before)
            with self.assertRaisesRegex(ValueError, "overwrite"):
                convert(workspace, workspace, identity=identity)
