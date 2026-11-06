"""Catch active AXI BFM attachment to a real CPU-driven iDMA response.

The generated SoC may expose a read-only probe mirror of the DMA R
channel even while ProbeEnable=0. Cocotbext-axi AxiMaster must never be
constructed on that mirror: it interprets actual hardware responses as
unexpected IDs and can consume signals before the passive AXI checker.
This is a fast ownership policy gate without launching Verilator.
"""
import ast
from pathlib import Path
import unittest
import yaml

ROOT = Path(__file__).resolve().parents[1]


class CpuDmaProbeTests(unittest.TestCase):
    def test_bfm_is_only_instantiated_when_cpu_dma_mode_is_disabled(self):
        module = ast.parse((ROOT/"dv/full_chip/test_boot.py").read_text())
        fn = next(n for n in module.body if isinstance(n, ast.AsyncFunctionDef)
                  and n.name == "execute_cold_boot")
        calls = [n for n in ast.walk(fn)
                 if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)
                 and n.func.id == "AxiMaster"]
        self.assertEqual(len(calls), 1, "only one optional probe BFM is allowed")
        guarded = [
            node for node in ast.walk(fn) if isinstance(node, ast.If)
            and isinstance(node.test, ast.BoolOp)
            and isinstance(node.test.op, ast.And)
            and ast.unparse(node.test) == "not cpu_dma_mode and host is None"
            and calls[0] in list(ast.walk(node))
        ]
        self.assertEqual(len(guarded), 1,
                         "AxiMaster must be disabled for both real CPU/DMA and PCIe host")


    def test_cpu_dma_first_when_suite_is_fast_fail(self):
        cfg = yaml.safe_load((ROOT/"config/regression.yaml").read_text())
        self.assertEqual(cfg["suites"]["chip"][0], "chip-cpu-dma")
        self.assertIn("chip-boot", cfg["suites"]["chip"])
        self.assertIn("chip-dma", cfg["suites"]["chip"])
        mk = (ROOT/"Makefile").read_text()
        self.assertIn("$(if $(filter 1,$(FAST_FAIL)),--fail-fast)", mk)
