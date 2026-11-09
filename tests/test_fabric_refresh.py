"""Main Fabric publication requires contemporaneous measured RTL evidence."""
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
import fabric_refresh as refresh

SHA = "a" * 40


class FabricRefreshTests(unittest.TestCase):
    def test_no_current_measurements_dispatch_once_and_never_loop(self):
        self.assertEqual(refresh.decision(SHA, 0, []), "dispatch")
        run = {"head_sha": SHA, "head_branch": "main",
               "event": "workflow_dispatch", "status": "queued",
               "conclusion": None}
        self.assertEqual(refresh.decision(SHA, 0, [run]), "in_progress")
        self.assertEqual(refresh.decision(SHA, 0, [
            {**run, "status": "completed", "conclusion": "failure"}]),
            "qualification_failed")
        self.assertEqual(refresh.decision(SHA, 0, [
            {**run, "status": "completed", "conclusion": "success"}]),
            "qualified_unpublished")
        self.assertEqual(refresh.decision(SHA, 3, []), "publish")
        self.assertEqual(refresh.decision(SHA, 0, [
            {**run, "head_sha": "b"*40, "status": "completed",
             "conclusion": "success"}]), "dispatch")
        self.assertEqual(refresh.decision(SHA, 0, [
            {**run, "head_branch": "feature", "status": "completed",
             "conclusion": "success"}]), "dispatch")

    def test_exact_source_site_measured_clock_and_stages(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp) / "site"
            (root / "data").mkdir(parents=True)
            (root / "data/site.json").write_text(json.dumps({"source_sha": SHA}))
            def fabric(measured, stages, historical, clock):
                (root / "data/fabric.json").write_text(json.dumps({
                    "latency_table": {
                        "evidence_coverage": {
                            "current_measured_routes": measured,
                            "current_stage_observations": stages,
                            "historical_observations": historical},
                        "reference_clock": {"measured_period_ps": clock}}}))
            fabric(64, 128, 1515, 10000)
            self.assertEqual(refresh.site_coverage(root, SHA),
                             {"measured": 64, "stages": 128, "historical": 1515})
            fabric(0, 0, 1515, None)
            self.assertEqual(refresh.site_coverage(root, SHA)["measured"], 0)
            fabric(64, 0, 1515, 10000)
            with self.assertRaisesRegex(ValueError, "stage/clock"):
                refresh.site_coverage(root, SHA)
            fabric(64, 128, 1515, None)
            with self.assertRaisesRegex(ValueError, "stage/clock"):
                refresh.site_coverage(root, SHA)
            fabric(64, 128, 1515, 10000)
            with self.assertRaisesRegex(ValueError, "exact main"):
                refresh.site_coverage(root, "b"*40)

    def test_main_guard_dispatch_and_refuses_unverified_releases(self):
        env = {"GITHUB_REF": "refs/heads/main",
               "GITHUB_EVENT_NAME": "workflow_dispatch", "GITHUB_SHA": SHA}
        calls = []
        def request(repository, token, path, *, body=None):
            calls.append((path, body))
            if path.endswith("/runs?branch=main&event=workflow_dispatch&per_page=100"):
                return {"workflow_runs": []}
            if path.endswith("/dispatches"):
                self.assertEqual(body, {"ref": "main"})
                return {}
            raise AssertionError(path)
        with patch.dict(os.environ, env), patch.object(
                refresh, "github_request", side_effect=request):
            with self.assertRaisesRegex(RuntimeError, "requested real main RTL"):
                refresh.guard_main(SHA, 0, 1500, "r987r/xezim-hello-world", "token")
        self.assertEqual(len(calls), 2)
        with patch.dict(os.environ, {**env, "GITHUB_REF": "refs/pull/42/merge"}):
            with self.assertRaisesRegex(ValueError, "only for exact main"):
                refresh.guard_main(SHA, 0, 1500, "r987r/xezim-hello-world", "token")

    def test_green_exact_sha_without_public_rows_is_a_publishing_bug(self):
        run = {"head_sha": SHA, "head_branch": "main",
               "event": "workflow_dispatch", "status": "completed",
               "conclusion": "success"}
        with patch.dict(os.environ, {
            "GITHUB_REF": "refs/heads/main", "GITHUB_EVENT_NAME": "workflow_dispatch",
            "GITHUB_SHA": SHA}), patch.object(
                refresh, "github_request",
                return_value={"workflow_runs": [run]}) as mocked:
            with self.assertRaisesRegex(RuntimeError, "PUBLICATION BUG"):
                refresh.guard_main(SHA, 0, 1515, "r987r/xezim-hello-world", "token")
            self.assertEqual(mocked.call_count, 1)


if __name__ == "__main__":
    unittest.main()
