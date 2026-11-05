import unittest
from tools.subsystem_plugin_contract import Port, SubsystemContract, Registry


class SubsystemPluginContractTests(unittest.TestCase):
    def setUp(self):
        self.r = Registry()
        for kind, direction, role, clock in [
            ("ethernet", "output", "initiator", "mac_clk"),
            ("pcie", "input", "target", "pcie_clk"),
        ]:
            self.r.register(SubsystemContract(
                kind, (clock,), (Port("axi", "axi4", direction, role, 64, clock),),
                "emitter_" + kind))

    def test_clock_crossing_requires_proven_adapter(self):
        with self.assertRaisesRegex(ValueError, "clock-domain"):
            self.r.check_link("ethernet", "axi", "pcie", "axi")
        self.assertEqual(self.r.check_link("ethernet", "axi", "pcie", "axi", cdc=True),
                         {"protocol": "axi4", "bits": 64, "cdc_required": True,
                          "evidence": "declarative_only"})

    def test_unknown_and_duplicate_refused(self):
        with self.assertRaises(ValueError):
            self.r.resolve("none")
        with self.assertRaises(ValueError):
            self.r.register(self.r.resolve("pcie"))
        with self.assertRaises(ValueError):
            self.r.check_link("ethernet", "missing", "pcie", "axi")

    def test_nonexistent_clock_and_duplicate_ports_refused(self):
        with self.assertRaisesRegex(ValueError, "port clock"):
            SubsystemContract("x", ("clk",),
                              (Port("a", "axi4", "input", "target", 64, "other"),), "x")
        p = Port("a", "axi4", "input", "target", 64, "clk")
        with self.assertRaisesRegex(ValueError, "duplicate"):
            SubsystemContract("x", ("clk",), (p,p), "x")


if __name__ == "__main__":
    unittest.main()
