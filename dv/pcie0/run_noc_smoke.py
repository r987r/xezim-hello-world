"""Run PCIe bridge through one generated FlooNoC and actual tc_sram RTL."""
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


def run(*, bar_relocate: bool = False):
    pin = source_contract()
    patched = assert_iverilog_clean()
    cfg = regress.load_config(ROOT / "config/regression.yaml")
    resolver = regress.Resolver(cfg)
    noc_files, noc_inc, noc_defines = resolver.sources({"sources": "noc"})
    manifest = json.loads((ROOT / "gen/noc/floonoc/manifest.json").read_text())
    actual = manifest["networks"].get("pcie0_local_data")
    if not actual or actual["status"] != "real_upstream_structural_RTL":
        raise RuntimeError("PCIe0 FlooNoC generation evidence missing")
    generated = [str(ROOT / "gen/noc/floonoc" / actual[key])
                 for key in ("package", "top")]
    vendor = ROOT / ".tools/verilog_pcie"
    files = list(dict.fromkeys(
        noc_files + generated + [str(ROOT / "rtl/adapters/axi_sram_target.sv"),
                                 str(ROOT / "dv/pcie_link/bar0_noc_translate.sv"),
                                 str(patched)]
        + [str(vendor / p) for p in pin["rtl_modules"]
           if p != "rtl/pcie_axi_master.v"]
        + [str(ROOT / "dv/pcie0/pcie_noc_tb.sv")]
    ))
    includes = list(dict.fromkeys(noc_inc))
    defs = {}
    for item in noc_defines:
        name, _, value = item.partition("=")
        defs[name] = value or "1"
    os.environ["PYTHONPATH"] = os.pathsep.join(
        [str(ROOT), str(ROOT / "dv/pcie0"),
         str(vendor / "tb/pcie_axi_master"), os.environ.get("PYTHONPATH", "")]
    )
    os.environ["MAKEFLAGS"] = "-j2"
    from cocotb.runner import get_runner
    output = ROOT / (".tools/pcie0/noc_relocated_build" if bar_relocate
                     else ".tools/pcie0/noc_build")
    output.mkdir(parents=True, exist_ok=True)
    simulator = get_runner("verilator")
    # Compile generated package before its NoC module.
    assert files.index(generated[0]) < files.index(generated[1])
    try:
        simulator.build(
            sources=files, includes=includes, defines=defs,
            hdl_toplevel="pcie_noc_tb", build_dir=output,
            parameters={"BAR0_RELOCATE": int(bar_relocate)},
            build_args=["--timing", "--assert", "-Wno-fatal"],
            always=True, waves=False, log_file=output / "build.log"
        )
    except Exception:
        diagnostic = output / "build.log"
        if diagnostic.exists():
            lines = diagnostic.read_text(errors="replace").splitlines()
            errors = [line for line in lines if line.startswith(("%Error", "%Warning"))]
            print("PCIe NoC build diagnostics:", *(errors[:60] or lines[-60:]), sep="\n", file=sys.stderr, flush=True)
        raise
    result = simulator.test(
        hdl_toplevel="pcie_noc_tb", hdl_toplevel_lang="verilog",
        test_module="noc_smoke", test_dir=ROOT / "dv/pcie0",
        results_xml=str(output / "results.xml"),
        log_file=output / "simulation.log",
    )
    if not Path(result).is_file():
        transcript = output / "simulation.log"
        details = transcript.read_text(errors="replace") if transcript.exists() else "(no simulation log)"
        print("PCIe real NoC/SRAM simulator failed before writing results XML:",
              details[-12000:], sep="\n", file=sys.stderr, flush=True)
        raise RuntimeError("missing Cocotb results XML: see simulator log above")
    tests = ElementTree.parse(result).findall(".//testcase")
    if not tests or any(
        any(t.find(tag) is not None for tag in ("failure", "error", "skipped"))
        for t in tests
    ):
        raise RuntimeError("real NoC/SRAM regression failed")
    print("PCIE0_BAR_RELOCATED_NOC_SRAM_PASS" if bar_relocate
          else "PCIE0_REAL_NOC_SRAM_REGRESSION_PASS")


if __name__ == "__main__":
    run(bar_relocate=False)  # preserve established fast TLP-only mode
    run(bar_relocate=True)   # independent host-BAR->FlooNoC byte proof
