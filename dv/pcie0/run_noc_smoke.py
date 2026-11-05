"""Run isolated PCIe bridge on the *existing* generated SoC RTL (no generator edits)."""
import json
import os
from pathlib import Path
import sys
from xml.etree import ElementTree

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT / "tools"), str(ROOT / "dv/pcie0")]
import ip_fetch
import regress
from prepare_rtl import assert_iverilog_clean
from run_rtl_smoke import source_contract


def run():
    pin = source_contract()
    patched = assert_iverilog_clean()
    cfg = regress.load_config(ROOT / "config/regression.yaml")
    resolver = regress.Resolver(cfg)
    for name in cfg["tests"]["chip-boot"].get("ip", []):
        ip_fetch.fetch(name)
    noc_files, noc_inc, noc_defines = resolver.sources({"sources": "noc"})
    chip_files, chip_inc, chip_defines = resolver.sources({"sources": "chip_boot"})
    manifest = json.loads((ROOT / "gen/noc/floonoc/manifest.json").read_text())
    actual = manifest["networks"].get("compute0_local_data")
    if not actual or actual["status"] != "real_upstream_structural_RTL":
        raise RuntimeError("compute0 FlooNoC generation evidence missing")
    generated = []
    for _, entry in sorted(manifest["networks"].items()):
        generated.append(str(ROOT / "gen/noc/floonoc" / entry["package"]))
    for _, entry in sorted(manifest["networks"].items()):
        generated.append(str(ROOT / "gen/noc/floonoc" / entry["top"]))
    vendor = ROOT / ".tools/verilog_pcie"
    files = list(dict.fromkeys(
        noc_files + chip_files + generated + [str(patched)]
        + [str(vendor / p) for p in pin["rtl_modules"]
           if p != "rtl/pcie_axi_master.v"]
        + [str(ROOT / "dv/pcie0/pcie_noc_tb.sv")]
    ))
    includes = list(dict.fromkeys(noc_inc + chip_inc))
    defs = {}
    for item in noc_defines + chip_defines:
        name, _, value = item.partition("=")
        defs[name] = value or "1"
    os.environ["PYTHONPATH"] = os.pathsep.join(
        [str(ROOT), str(ROOT / "dv/pcie0"),
         str(vendor / "tb/pcie_axi_master"), os.environ.get("PYTHONPATH", "")]
    )
    os.environ["MAKEFLAGS"] = "-j2"
    from cocotb.runner import get_runner
    output = ROOT / ".tools/pcie0/noc_build"
    output.mkdir(parents=True, exist_ok=True)
    simulator = get_runner("verilator")
    simulator.build(
        sources=files, includes=includes, defines=defs,
        hdl_toplevel="pcie_noc_tb", build_dir=output,
        build_args=["--timing", "--assert", "-Wno-fatal"],
        always=True, waves=False, log_file=output / "build.log"
    )
    result = simulator.test(
        hdl_toplevel="pcie_noc_tb", hdl_toplevel_lang="verilog",
        test_module="noc_smoke", test_dir=ROOT / "dv/pcie0",
        results_xml=str(output / "results.xml"),
        log_file=output / "simulation.log",
    )
    tests = ElementTree.parse(result).findall(".//testcase")
    if not tests or any(
        any(t.find(tag) is not None for tag in ("failure", "error", "skipped"))
        for t in tests
    ):
        raise RuntimeError("real NoC/SRAM regression failed")
    print("PCIE0_REAL_NOC_SRAM_REGRESSION_PASS")


if __name__ == "__main__":
    run()
