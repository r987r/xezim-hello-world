"""Static guard: all reported AXI cocotb simulations attach before their clock.

Monitor configuration and cocotb entrypoints are both checked. This catches
accidental late attachment, absent reporting, or an early monitor shutdown
without modifying the boot / DMA / NoC testbenches.

Stand-alone tests that do not instantiate the SoC fabric need a separate
passive-AXI catalog before report. The explicitly documented exception below
preserves an in-flight DMA PR; it is not an exception for any full-chip test.
"""
from __future__ import annotations

import ast
from pathlib import Path
import unittest

import yaml


ROOT = Path(__file__).resolve().parents[1]

# Standalone DMA RTL exercises a cocotbext-axi AXI slave, not a FlooNoC
# source/link/target catalog. PR #14 is integrating the separate SoC-level
# chip-dma regression with a full passive AXI report. Do not quietly expand
# this exemption to chip-level or networked tests.
STANDALONE_NO_FABRIC_EXEMPTIONS = {
    "dma-rtl": "standalone DMA core and cocotbext-axi sink, no FlooNoC topology",
}


def _calls(node, target: str) -> bool:
    return any(
        isinstance(part, ast.Call) and (
            (isinstance(part.func, ast.Name) and part.func.id == target) or
            (isinstance(part.func, ast.Attribute) and part.func.attr == target)
        ) for part in ast.walk(node)
    )


def _is_test(node: ast.AST) -> bool:
    if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
        return False
    return any(
        isinstance(deco, ast.Call) and (
            (isinstance(deco.func, ast.Attribute) and deco.func.attr == "test") or
            (isinstance(deco.func, ast.Name) and deco.func.id == "test")
        ) for deco in node.decorator_list
    )


def check_module(text: str) -> None:
    tree = ast.parse(text)
    functions = {
        node.name: node for node in tree.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    }
    test_functions = [node for node in functions.values() if _is_test(node)]
    if not test_functions:
        raise AssertionError("reported AXI cocotb module has no test entrypoint")

    checked = set()
    for entry in test_functions:
        # A test may attach directly or through a same-module setup helper.
        helper_names = [
            name for name in functions
            if name == entry.name or _calls(entry, name)
        ]
        found = False
        for name in helper_names:
            fn = functions[name]
            attach_lines = [n.lineno for n in ast.walk(fn)
                            if isinstance(n, ast.Call) and (
                                (isinstance(n.func, ast.Name) and n.func.id == "attach_observers") or
                                (isinstance(n.func, ast.Attribute) and n.func.attr == "attach_observers")
                            )]
            clocks = [n.lineno for n in ast.walk(fn)
                      if isinstance(n, ast.Call) and (
                          (isinstance(n.func, ast.Name) and n.func.id == "Clock") or
                          (isinstance(n.func, ast.Attribute) and n.func.attr == "Clock")
                      )]
            if attach_lines and clocks:
                if min(attach_lines) >= min(clocks):
                    raise AssertionError(f"{name}: AXI observer attaches after DUT clock")
                # Catch the earlier DDR bug: cancel/kill must not be in the
                # same setup or test path while data transactions continue.
                if _calls(fn, "kill") or _calls(fn, "cancel"):
                    raise AssertionError(f"{name}: AXI observer may stop before test end")
                found = True
                checked.add(name)
                break
        if not found:
            raise AssertionError(f"{entry.name}: no observer attached before DUT clock")
    if not checked:
        raise AssertionError("no monitored cocotb setup was validated")


def _source_path(profile: dict) -> Path:
    module = profile.get("module")
    test_dir = profile.get("test_dir")
    if not isinstance(module, str) or not isinstance(test_dir, str):
        raise AssertionError("reported AXI test missing module or test directory")
    if "." in module:
        path = ROOT / (module.replace(".", "/") + ".py")
    else:
        path = ROOT / test_dir / (module + ".py")
    if not path.is_file():
        raise AssertionError(f"missing cocotb module: {path}")
    return path


class MonitorLifecyclePolicyTests(unittest.TestCase):
    def test_configured_reported_cocotb_entrypoints_are_monitored(self):
        config = yaml.safe_load((ROOT / "config/regression.yaml").read_text())
        covered = set()
        for name, profile in config["tests"].items():
            if profile.get("engine") != "cocotb-verilator":
                continue
            report = profile.get("report")
            if not report:
                self.assertIn(
                    name, STANDALONE_NO_FABRIC_EXEMPTIONS,
                    f"{name}: AXI cocotb simulation lacks a passive capture/report",
                )
                continue
            self.assertIn("axi", report, f"{name}: report omitted AXI monitoring")
            path = _source_path(profile)
            with self.subTest(test=name, module=str(path.relative_to(ROOT))):
                check_module(path.read_text())
            covered.add(name)
        self.assertTrue({"supernoc", "supernoc-negative", "chip-boot",
                         "chip-boot-negative"} <= covered)

    def test_reject_unmonitored_cocotb_entrypoint(self):
        bad = """
import cocotb
from cocotb.clock import Clock
@cocotb.test()
async def smoke(dut):
    cocotb.start_soon(Clock(dut.clk, 10, units="ns").start())
"""
        with self.assertRaisesRegex(AssertionError, "no observer"):
            check_module(bad)

    def test_reject_late_attachment(self):
        bad = """
import cocotb
from cocotb.clock import Clock
@cocotb.test()
async def smoke(dut):
    cocotb.start_soon(Clock(dut.clk, 10, units="ns").start())
    attach_observers(dut)
"""
        with self.assertRaisesRegex(AssertionError, "after DUT clock"):
            check_module(bad)

    def test_reject_monitor_shutdown_in_test_setup(self):
        bad = """
import cocotb
from cocotb.clock import Clock
@cocotb.test()
async def smoke(dut):
    attach_observers(dut)
    cocotb.start_soon(Clock(dut.clk, 10, units="ns").start())
    monitor.kill()
"""
        with self.assertRaisesRegex(AssertionError, "stop before"):
            check_module(bad)

    def test_allowed_setup_helper_has_startup_monitor(self):
        good = """
import cocotb
from cocotb.clock import Clock
async def setup(dut):
    attach_observers(dut)
    cocotb.start_soon(Clock(dut.clk, 10, units="ns").start())
@cocotb.test()
async def smoke(dut):
    await setup(dut)
    await run_data(dut)
"""
        check_module(good)

    def test_reported_cocotb_tests_receive_run_plan(self):
        runner = (ROOT / "tools/regress.py").read_text()
        self.assertIn("env['SOC_RUN_PLAN'] = str(plan_file)", runner)
        self.assertIn("not summary['capture_bound']", runner)
        trace = (ROOT / "dv/common/axi_trace.py").read_text()
        self.assertIn("'capture_start'", trace)
        self.assertIn("def attach_observers(dut)", trace)
        self.assertIn("self.consume(", trace)


if __name__ == "__main__":
    unittest.main()
