"""Offline tests of the post-deploy public CSR release gate."""
import copy
import hashlib
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
from check_published_csr import validate


class PublishedCsrTests(unittest.TestCase):
    def setUp(self):
        validate.expected_sha = "a" * 40
        self.site = {"source_sha": "a" * 40}
        self.html = ('id="am-csr-browser" source-only reference(s) '
                     'id="ddr-csr-variants-data" data/csr-source-coverage.json')
        self.coverage = {
            "schema_version": 1, "unacknowledged": [],
            "instances": [
                {"instance": "compute0.dma", "source_only_registers": 4},
                {"instance": "compute1.dma", "source_only_registers": 4},
                {"instance": "ethernet0.ctrl", "source_only_registers": 30},
            ],
        }
        self.ddr = [{
            "run_id": 123,
            "catalog": {
                "variant": "ddr_real",
                "regions": [{
                    "name": "memory0.ctrl",
                    "size": "0x4000",
                    "registers": [{
                        "name": "sdram_dfii_control",
                        "definition_status":
                            "native_LiteDRAM_generated_CSR_not_bus_coverage",
                    }],
                }],
            },
        }]

    def test_qualified_public_release(self):
        self.assertEqual(validate(self.site, self.html, self.coverage, self.ddr), 1)

    def test_reject_stale_public_site(self):
        with self.assertRaisesRegex(ValueError, "source SHA"):
            validate({"source_sha": "b" * 40}, self.html, self.coverage, self.ddr)

    def test_reject_missing_browser_or_source_only_references(self):
        with self.assertRaisesRegex(ValueError, "missing"):
            validate(self.site, "", self.coverage, self.ddr)
        missing = copy.deepcopy(self.coverage)
        missing["instances"].pop()
        with self.assertRaisesRegex(ValueError, "ethernet0.ctrl"):
            validate(self.site, self.html, missing, self.ddr)

    def test_reject_missing_or_unqualified_ddr(self):
        with self.assertRaisesRegex(ValueError, "no qualified"):
            validate(self.site, self.html, self.coverage, [])
        untrusted = copy.deepcopy(self.ddr)
        untrusted[0]["catalog"]["regions"][0]["registers"][0]["definition_status"] = "manual"
        with self.assertRaisesRegex(ValueError, "qualified native"):
            validate(self.site, self.html, self.coverage, untrusted)

    def test_production_dma_header_is_bound_to_published_source_digest(self):
        header = "/* generated */\\n#define SOC_DMA_SHIM_HEAD_LO_OFFSET 0\\n#define SOC_DMA_SHIM_STATUS_OFFSET 12\\n"
        self.site["production_dma_header_sha256"] = hashlib.sha256(header.encode()).hexdigest()
        html = self.html + ' <a href="data/soc_dma_shim_regs.h">Production DMA header</a>'
        self.assertEqual(validate(self.site, html, self.coverage, self.ddr, header), 1)
        with self.assertRaisesRegex(ValueError, "differs"):
            validate(self.site, html, self.coverage, self.ddr, header + "changed")
        with self.assertRaisesRegex(ValueError, "missing production"):
            validate(self.site, self.html, self.coverage, self.ddr, header)

    def test_reject_unregistered_new_subsystem(self):
        coverage = copy.deepcopy(self.coverage)
        coverage["unacknowledged"] = ["new0.ctrl"]
        with self.assertRaisesRegex(ValueError, "unknown CSR"):
            validate(self.site, self.html, coverage, self.ddr)


if __name__ == "__main__":
    unittest.main()
