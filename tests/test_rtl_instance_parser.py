"""Contract tests for real slang CST structure and fail-closed RTL instance parsing."""
from pathlib import Path
import json
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
import rtl_instance_parser as p


def instance(name, module, links):
    return {
        "kind": "HierarchyInstantiation", "type": module,
        "instances": [{
            "kind": "HierarchicalInstance",
            "decl": {"kind": "InstanceName", "name": name},
            "openParen": "(", "connections": [
                {"kind": "NamedPortConnection", "dot": ".", "name": port,
                 "openParen": "(", "expr": {"kind": "IdentifierName", "identifier": expr},
                 "closeParen": ")"} for port, expr in links
            ], "closeParen": ")"
        }], "semi": ";"
    }


def module(name, children):
    return {"kind": "ModuleDeclaration",
            "header": {"kind": "ModuleHeader", "moduleKeyword": "module", "name": name},
            "members": children, "endmodule": "endmodule"}


def payload(name, children):
    return {"syntaxTrees": [{"kind": "SyntaxTree", "root": {
        "kind": "CompilationUnit", "members": [module(name, children)]}}]}


class RealSlangCSTTests(unittest.TestCase):
    def test_named_bindings_and_independent_data_config(self):
        obj = payload("soc_top", [
            instance("u_noc", "soc_noc", [("clk_i", "clk_i"), ("rst_ni", "rst_ni")]),
            instance("u_ctrl", "config_master", [("cfg_req_i", "cfg_req")]),
        ])
        parsed = p.parse_tree(obj, "gen/chip/soc_top.sv")
        self.assertEqual(parsed[0]["name"], "soc_top")
        self.assertEqual([a["name"] for a in parsed[0]["instances"]], ["u_noc", "u_ctrl"])
        self.assertEqual(parsed[0]["instances"][0]["ports"][0]["port"], "clk_i")
        self.assertEqual(parsed[0]["instances"][0]["ports"][0]["expression"], "clk_i")
        self.assertEqual(parsed[0]["instances"][1]["ports"][0]["expression"], "cfg_req")

    def test_build_validates_real_instance_composition(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "gen/chip").mkdir(parents=True)
            (root / "gen/supernoc").mkdir(parents=True)
            (root / "gen/chip/soc_top.sv").write_text("module soc_top; endmodule\n")
            (root / "gen/supernoc/soc_noc.sv").write_text("module soc_noc; endmodule\n")
            data = {
                "soc_top": payload("soc_top", [instance("u_noc", "soc_noc", [("clk_i", "clk_i")])]),
                "soc_noc": payload("soc_noc", [
                    instance("u_data", "floo_data_noc", [("clk_i", "clk_i")]),
                    instance("u_config", "floo_config_noc", [("clk_i", "clk_i")]),
                ])
            }
            with patch.object(p, "run_slang", side_effect=lambda root,binary,source:data[source.stem]), \
                 patch.object(p.shutil, "which", return_value="/mock/slang"):
                result = p.build(root, slang="/mock/slang")
            self.assertEqual(result["summary"]["noc_instances"], 2)
            self.assertEqual(result["summary"]["named_port_bindings"], 3)
            self.assertFalse(result["profile_specific_elaboration_proven"])

    def test_unknown_missing_slang_is_not_declared_valid(self):
        with patch.object(p.shutil, "which", return_value=None):
            with self.assertRaisesRegex(ValueError, "compiler missing"):
                p.build(ROOT, slang="missing")

    def test_rejects_empty_cst(self):
        with self.assertRaisesRegex(ValueError, "no valid syntax trees"):
            p.parse_tree({"syntaxTrees": []}, "bad.sv")


if __name__ == "__main__":
    unittest.main()
