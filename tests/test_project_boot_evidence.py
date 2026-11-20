"""Producer archive -> trusted Pages -> isolated per-project boot verdict."""
from copy import deepcopy
from hashlib import sha256
from io import BytesIO
import json
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
import unittest
from zipfile import ZipFile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
from project_catalog import projects
from project_smoke import PHASES, check_native_boot_log
from project_boot_evidence import LOGS, RESULT, publish
from publish_site import collect_project_boot, project_pages

REPO = "r987r/xezim-hello-world"
SHA = "a" * 40
SITE = "b" * 40


class Actions:
    repository = REPO

    def __init__(self, data, *, equivalent=False):
        self.data = data
        self.equivalent = equivalent

    def request(self, path, *, binary=False):
        if binary:
            assert path.endswith("/actions/artifacts/123/zip")
            return self.data
        if self.equivalent and path.endswith(("/" + SHA, "/" + SITE)):
            return {"tree": {"sha": "e" * 40}}
        raise AssertionError(path)


class ProjectBootEvidenceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.catalog = {p["id"]: p for p in projects(ROOT)}

    def setUp(self):
        self.project = self.catalog["xezim_ethernet_cpu_ddr_pcie"]
        self.pid = self.project["id"]
        cores = len(self.project["compute"])
        self.logs = {
            LOGS[0]: b"native build output",
            LOGS[1]: "\n".join([PHASES[0],
                *[f"hello world from CPU{i} (firmware mailbox)" for i in range(cores)],
                PHASES[1], PHASES[2],
                f"PASS fullchip: {cores} real CPUs, shared NoCs, cold boot, init/run/check"
                ]).encode(),
        }
        self.result = dict(
            schema_version=1, project_id=self.pid, engine="verilator-native",
            test="native-selected-real-cpu-cold-boot", source_config=self.project["config"],
            source_config_sha256=self.project["config_sha256"], filelist_sha256="f" * 64,
            cpu_count=cores, status="passed", simulation_returncode=0, tested_sha=SHA,
            workflow_run_id="42", workflow_attempt="2", ddr_data_qualified=False,
            pcie_qualified=False, ethernet_qualified=False,
            log_sha256={k: sha256(v).hexdigest() for k, v in self.logs.items()},
            observations=check_native_boot_log(self.logs[LOGS[1]].decode(), cores),
        )
        self.run_data = dict(id=42, run_attempt=2, head_sha=SHA, head_branch="main",
                             status="completed", conclusion="success",
                             event="workflow_dispatch", head_repository={"full_name": REPO})

    def collect(self, folder, *, result=None, logs=None, run=None, name=None,
                site_sha=SHA, equivalent=False):
        buffer = BytesIO()
        with ZipFile(buffer, "w") as archive:
            archive.writestr(RESULT, json.dumps(self.result if result is None else result))
            for key, payload in (self.logs if logs is None else logs).items():
                archive.writestr(key, payload)
        raw = buffer.getvalue()
        artifact = dict(id=123, name=name or f"project-boot-{self.pid}-42-2",
                        digest="sha256:" + sha256(raw).hexdigest(), size_in_bytes=len(raw))
        cache = folder / "42-2"
        cache.mkdir(exist_ok=True)
        collect_project_boot(Actions(raw, equivalent=equivalent),
                             dict(max_archive_mib=10, max_expanded_mib=10),
                             cache, run or self.run_data, artifact, self.catalog,
                             site_sha, {}, {})

    def test_project_boot_renders_only_for_its_owner(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            evidence, out = root / "evidence", root / "site"
            evidence.mkdir()
            out.mkdir()
            (out / "explorer.html").write_text("original hierarchy")
            self.collect(evidence)
            boot = publish(evidence, out, SHA)[self.pid]
            project_pages(out, list(self.catalog.values()), [], REPO, SHA,
                          boots={self.pid: boot})
            base = out / "projects" / self.pid
            for page in ("index.html", "runs.html"):
                text = (base / page).read_text()
                self.assertIn("Current source PASS", text)
                self.assertIn("boot/42-2/native-build.log", text)
                self.assertIn("boot/42-2/native-sim.log", text)
                self.assertIn("Boot is not routed protocol or payload qualification", text)
            payload = json.loads((base / "data/project.json").read_text())
            self.assertFalse(payload["current_source_functional_pass"])
            self.assertEqual(payload["runs"], [])
            self.assertEqual(payload["native_boot"]["tested_sha"], SHA)
            self.assertNotIn("Current source PASS",
                             (out / "projects/xezim_soc_dv/runs.html").read_text())
            self.assertNotIn("simulation passed", (out / "index.html").read_text())
            self.assertEqual((base / boot["logs"][LOGS[1]]).read_bytes(), self.logs[LOGS[1]])

    def test_stale_source_not_current_and_failed_result_not_pass(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            result = dict(self.result, status="failed")
            self.collect(root, result=result, run=dict(self.run_data, conclusion="failure"))
            boot = publish(root, root / "site", SITE)[self.pid]
            self.assertEqual(boot["status"], "failed")
            self.assertFalse(boot["current_source"])

    def test_only_equivalent_merged_pr_tree_can_be_current(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            run = dict(self.run_data, head_branch="boot-fix", event="pull_request",
                       verified_merged_pr=300)
            self.collect(root, run=run, site_sha=SITE, equivalent=True)
            boot = publish(root, root / "site", SITE)[self.pid]
            self.assertEqual(boot["tested_sha"], SHA)
            self.assertTrue(boot["current_source"])

    def test_reject_wrong_project_source_attempt_and_incomplete_proof(self):
        bad_log = b"compiler exited successfully"
        log_hashes = dict(self.result["log_sha256"], **{LOGS[1]: sha256(bad_log).hexdigest()})
        cases = [
            dict(name=f"project-boot-{self.pid}-42-1"),
            dict(result=dict(self.result, workflow_attempt="1")),
            dict(result=dict(self.result, project_id="xezim_soc_dv")),
            dict(result=dict(self.result, source_config_sha256="c" * 64)),
            dict(result=dict(self.result, tested_sha="c" * 40)),
            dict(result=dict(self.result, ethernet_qualified=True)),
            dict(logs={LOGS[0]: self.logs[LOGS[0]]}),
            dict(logs=dict(self.logs, **{LOGS[1]: bad_log}),
                 result=dict(self.result, log_sha256=log_hashes)),
            dict(logs=dict(self.logs, **{"unexpected.html": b"not a native log"})),
            dict(run=dict(self.run_data, event="pull_request")),
        ]
        for case in cases:
            with self.subTest(case=list(case)), TemporaryDirectory() as tmp:
                root = Path(tmp)
                with self.assertRaises(ValueError):
                    self.collect(root, **case)
                self.assertEqual(publish(root, root / "site", SHA), {})
