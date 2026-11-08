"""Verify tracing uses real saved graph edges and ignores disabled dependencies."""
import json
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
import signal_paths


def graph():
    return {
        "version": 1, "fileTable": ["rtl/example.sv"], "blackBoxes": [],
        "nodes": [
            {"id": 1, "kind": "Port", "name": "awvalid", "path": "soc.u0.awvalid",
             "bounds": [0, 0], "direction": "Out", "location": {"fileIndex": 0, "line": 1, "column": 1}},
            {"id": 2, "kind": "Assignment", "location": {"fileIndex": 0, "line": 5, "column": 1}},
            {"id": 3, "kind": "Port", "name": "awvalid", "path": "soc.u1.awvalid",
             "bounds": [0, 0], "direction": "In", "location": {"fileIndex": 0, "line": 8, "column": 1}},
            {"id": 4, "kind": "Port", "name": "fake", "path": "soc.u2.fake",
             "bounds": [0, 0], "direction": "In", "location": {"fileIndex": 0, "line": 11, "column": 1}},
        ],
        "edges": [
            {"source": 1, "target": 2, "bounds": [0, 0],
             "edgeKind": "None", "disabled": False},
            {"source": 2, "target": 3, "bounds": [0, 0],
             "edgeKind": "None", "disabled": False},
            {"source": 1, "target": 4, "bounds": [0, 0],
             "edgeKind": "None", "disabled": True},
        ]}


class SlangDependencyTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.file = Path(self.temp.name) / "netlist.json"
        self.file.write_text(json.dumps(graph()))

    def test_exact_path_and_locations(self):
        result = signal_paths.trace(self.file, "soc.u0.awvalid", "soc.u1.awvalid")
        self.assertTrue(result["found"])
        self.assertEqual(len(result["steps"]), 2)
        self.assertEqual(result["steps"][-1]["source_location"]["line"], 8)
        self.assertEqual(result["steps"][-1]["bit_bounds"], [0, 0])

    def test_no_fabricated_wire_when_edge_disabled(self):
        result = signal_paths.trace(self.file, "soc.u0.awvalid", "soc.u2.fake")
        self.assertFalse(result["found"])
        self.assertEqual(result["steps"], [])

    def test_limited_depth_is_not_proof_of_disconnection(self):
        result = signal_paths.trace(self.file, "soc.u0.awvalid",
                                    "soc.u1.awvalid", max_depth=1)
        self.assertFalse(result["found"])
        self.assertFalse(result["complete_under_limits"])

    def test_exhaustive_miss_is_distinct_from_depth_truncation(self):
        # The disabled source-to-fake edge cannot be used as proof of wiring.
        result = signal_paths.trace(self.file, "soc.u0.awvalid", "soc.u2.fake")
        self.assertFalse(result["found"])
        self.assertTrue(result["complete_under_limits"])
        limited = signal_paths.trace(self.file, "soc.u0.awvalid",
                                     "soc.u1.awvalid", max_depth=1)
        self.assertFalse(limited["complete_under_limits"])

    def test_duplicate_port_path_and_invalid_width_fail_closed(self):
        d = graph()
        duplicate = dict(d["nodes"][2])
        duplicate["id"] = 99
        duplicate["path"] = d["nodes"][0]["path"]
        d["nodes"].append(duplicate)
        self.file.write_text(json.dumps(d))
        with self.assertRaisesRegex(ValueError, "duplicate elaborated port path"):
            signal_paths.read_graph(self.file)
        d["nodes"].pop()
        d["nodes"][0]["bounds"] = [31, 0]  # Legal descending packed range.
        self.file.write_text(json.dumps(d))
        signal_paths.read_graph(self.file)
        d["nodes"][0]["bounds"] = [2, -1]
        self.file.write_text(json.dumps(d))
        with self.assertRaisesRegex(ValueError, "invalid elaborated port bounds"):
            signal_paths.read_graph(self.file)

    def test_fails_unknown_port_or_dangling_edges(self):
        with self.assertRaisesRegex(ValueError, "unknown elaborated port"):
            signal_paths.trace(self.file, "unknown.signal", "soc.u1.awvalid")
        d = graph()
        d["edges"][0]["target"] = 200
        self.file.write_text(json.dumps(d))
        with self.assertRaisesRegex(ValueError, "dangling"):
            signal_paths.read_graph(self.file)


if __name__ == "__main__":
    unittest.main()
