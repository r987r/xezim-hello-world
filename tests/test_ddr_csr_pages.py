"""Only qualified DDR native CSR run maps enter the published variant selector."""
import json
from pathlib import Path
import sys
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"tools"))
from publish_site import ddr_csr_views


class DdrCsrPagesTests(unittest.TestCase):
    def test_only_successful_native_csr_trace_is_listed(self):
        with tempfile.TemporaryDirectory() as tmp:
            output=Path(tmp)
            location=output/"runs"/"987-1"/"chip-ddr4-real"
            location.mkdir(parents=True)
            catalog={
                "schema_version":1,"variant":"ddr_real",
                "regions":[{"name":"memory0.ctrl","size":"0x4000",
                            "base":"0x40030000",
                            "registers":[{"name":"sdram_dfii_control",
                                          "definition_status":"native_LiteDRAM_generated_CSR_not_bus_coverage"}]}],
            }
            (location/"axi-transactions.json").write_text(json.dumps({
                "run":{"target":"chip-ddr4-real"},"sections":{"address_map":catalog}}))
            item={"target":"chip-ddr4-real","passed":True,"axi":True,
                  "run_id":987,"source_sha":"ab"*20,
                  "path":"runs/987-1/chip-ddr4-real/report.html"}
            views=ddr_csr_views([item],output)
            self.assertEqual(len(views),1)
            self.assertEqual(views[0]["catalog"]["variant"],"ddr_real")
            self.assertEqual(views[0]["run_id"],987)
            self.assertEqual(ddr_csr_views([{**item,"passed":False}],output),[])
            fake={**catalog,"variant":"architecture"}
            (location/"axi-transactions.json").write_text(json.dumps({
                "sections":{"address_map":fake}}))
            self.assertEqual(ddr_csr_views([item],output),[])
            fake={**catalog,"regions":[{**catalog["regions"][0],"registers":[]}]}
            (location/"axi-transactions.json").write_text(json.dumps({
                "sections":{"address_map":fake}}))
            self.assertEqual(ddr_csr_views([item],output),[])
            fake={**catalog,"regions":[{**catalog["regions"][0],
                    "registers":[{"definition_status":"SystemRDL_defined_not_RTL_proof"}]}]}
            (location/"axi-transactions.json").write_text(json.dumps({
                "sections":{"address_map":fake}}))
            self.assertEqual(ddr_csr_views([item],output),[])

    def test_default_page_has_variant_selector_but_no_fabricated_ddr(self):
        template=(ROOT/"tools/templates/site_address-map.html").read_text()
        self.assertIn('id="am-variant"',template)
        self.assertIn('id="ddr-csr-variants-data"',template)
        self.assertIn("ddrVariants.length",template)
        self.assertIn("selectVariant()",template)
        self.assertIn("PCIe_source_reference_not_build_qualified",template)
        self.assertNotIn('mr-test-select',template)


if __name__=="__main__":
    unittest.main()
