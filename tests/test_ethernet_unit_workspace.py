"""Pin existing Ethernet native unit behavior across archive changes."""
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import yaml

from tools.ethernet_unit_workspace import AXI_ROOT, LANES, LOCK, ROOT, fetched_provenance, sources_for, verify_transcript


class EthernetUnitWorkspaceTests(unittest.TestCase):
    def test_accepts_only_one_full_native_marker_per_lane(self):
        for lane, (_, top, _, _, _, fields) in LANES.items():
            marker = (f"PASS {top}" + "".join(f" {field}=5" for field in fields)).encode()
            with self.subTest(lane=lane):
                verify_transcript(lane, marker + b"\noriginal finish\n")
                for bad in (b"", b"banner " + marker, marker + b"\n" + marker,
                            marker[:-1], marker.replace(b"checks=", b"asserts=")):
                    with self.assertRaises(ValueError):
                        verify_transcript(lane, bad)
                for other in LANES.keys() - {lane}:
                    with self.assertRaises(ValueError):
                        verify_transcript(other, marker)

    def test_compiler_inputs_and_archive_dependencies_trigger_original_jobs(self):
        for lane, (_, _, _, _, upstream, _) in LANES.items():
            workflow = f".github/workflows/ethernet-{lane}.yml"
            data = yaml.safe_load((ROOT / workflow).read_text())
            paths = data[True]["pull_request"]["paths"]
            with self.subTest(lane=lane):
                for path in (*(source for source in sources_for(lane) if not source.startswith(AXI_ROOT)),
                             workflow, LOCK,
                             "tools/ethernet_unit_workspace.py", "tools/ethernet_frame_workspace.py",
                             "tools/run_workspace.py", "tools/test_identity.py",
                             "tests/test_ethernet_unit_workspace.py"):
                    self.assertIn(path, paths)
                self.assertEqual("tools/ip_fetch.py" in paths, bool(upstream))

    def test_wrong_pin_or_different_compiler_bytes_fail_before_execution(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            lock = root / LOCK
            lock.parent.mkdir()
            expected = "a" * 40
            lock.write_text(f"third_party:\n  verilog_axi: {{commit: {expected}}}\n")
            module = root / AXI_ROOT / "rtl/axi_dma_rd.v"
            module.parent.mkdir(parents=True)
            module.write_bytes(b"changed bytes")
            with patch("tools.ethernet_unit_workspace.git", return_value=b"b" * 40):
                with self.assertRaisesRegex(ValueError, "unexpected verilog_axi checkout"):
                    fetched_provenance(root, (module.name,))
            with patch("tools.ethernet_unit_workspace.git",
                       side_effect=[expected.encode(), b"pinned bytes"]):
                with self.assertRaisesRegex(ValueError, "differs from pinned source bytes"):
                    fetched_provenance(root, (module.name,))

    def test_queue_controller_needs_no_fetched_sources(self):
        self.assertEqual(fetched_provenance(Path("/nonexistent"), ()), {})
