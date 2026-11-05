import unittest
from tools.rtl_binding_audit import audit, require_clean


class RtlBindingAuditTests(unittest.TestCase):
    def setUp(self):
        self.inventory = {"modules": [
            {"name": "soc_top", "instances": [
                {"name": "u_noc", "ports": [
                    {"port": "clk_i", "expression": "clk"},
                    {"port": "rst_ni", "expression": "reset_n"},
                    {"port": "axi_i", "expression": "source_axi"}]}]}]}

    def test_pass_is_syntax_only(self):
        result = audit(self.inventory, {("soc_top", "u_noc"): {"clk_i", "rst_ni"}})
        self.assertTrue(result["pass"])
        self.assertIn("not_bit_level", result["evidence"])

    def test_missing_and_empty_port_fail_closed(self):
        req = {("soc_top", "u_noc"): {"clk_i", "wrong_port"}}
        out = audit(self.inventory, req)
        self.assertFalse(out["pass"])
        with self.assertRaisesRegex(ValueError, "missing parsed"):
            require_clean(out)
        self.inventory["modules"][0]["instances"][0]["ports"][0]["expression"] = ""
        out = audit(self.inventory, {("soc_top", "u_noc"): {"clk_i"}})
        self.assertEqual(out["findings"][0]["kind"], "unconnected_required_port")

    def test_ambiguous_instance_refused(self):
        self.inventory["modules"][0]["instances"].append(
            self.inventory["modules"][0]["instances"][0])
        with self.assertRaisesRegex(ValueError, "ambiguous"):
            audit(self.inventory, {})


if __name__ == "__main__":
    unittest.main()
