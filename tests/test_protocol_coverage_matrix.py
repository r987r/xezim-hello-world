import unittest
from tools.protocol_coverage_matrix import summarize, require_coverage


class CoverageTests(unittest.TestCase):
    def test_completed_axi_is_not_ethernet_or_pcie_coverage(self):
        report = {"schema_version": 1, "capture_complete": True, "issues": [],
                  "sources": [{"id": "noc0", "protocol": "axi4"}],
                  "records": [{"kind": "transaction", "protocol": "axi4", "source": "noc0",
                               "status": "complete", "start_ps": 12, "end_ps": 20}]}
        complete = summarize(report, ("axi4",))
        self.assertEqual(complete["status"], "coverage_complete")
        partial = summarize(report, ("axi4", "ethernet", "pcie_tlp"))
        self.assertEqual(partial["missing_required_protocols"], ["ethernet", "pcie_tlp"])
        with self.assertRaises(AssertionError):
            require_coverage(partial)

    def test_incomplete_transaction_fails(self):
        report = {"schema_version": 1, "capture_complete": True, "sources": [
                    {"id": "pcie", "protocol": "pcie_tlp"}],
                  "records": [{"kind": "transaction", "source": "pcie",
                               "protocol": "pcie_tlp", "status": "incomplete", "start_ps": 5}]}
        self.assertEqual(summarize(report, ("pcie_tlp",))["status"], "coverage_missing")

    def test_undeclared_monitor_refused(self):
        with self.assertRaises(ValueError):
            summarize({"schema_version": 1, "sources": [], "records": [
                {"source": "absent", "protocol": "axi4"}]}, ("axi4",))


if __name__ == "__main__":
    unittest.main()
