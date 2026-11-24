"""Run PCIe bridge through one generated FlooNoC and actual tc_sram RTL."""
import json
import os
from pathlib import Path
import subprocess
import sys
from xml.etree import ElementTree

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT / "tools"), str(ROOT / "dv/pcie0")]
import regress
from run_workspace import reserve_run, verify_artifact_inventory
from test_identity import relative_path, selected, sha
from prepare_rtl import assert_iverilog_clean
from run_rtl_smoke import source_contract

TOP = "pcie_noc_tb"
MODULE = "noc_smoke"
CASE = "host_to_real_floonoc_tc_sram"
BUILD_ARGS = ("--timing", "--assert", "-Wno-fatal")


def selected_plan(bar_relocate: bool):
    mode = "relocated" if bar_relocate else "legacy"
    target = f"pcie0-real-noc-{mode}"
    return target, {"target": target, "sources": f"pcie-local-noc-bar0-{mode}",
                    "engine": "cocotb-verilator", "top": TOP, "module": MODULE,
                    "logical_test": "host-tlp-to-local-sram",
                    "parameters": {"BAR0_RELOCATE": int(bar_relocate)},
                    "build_args": list(BUILD_ARGS)}


def _selected_filelist(files, includes, defines, bar_relocate):
    # Record the native Cocotb 1.9.2 Verilator source/option order; its
    # runner still owns the compiler command, work directory and VPI glue.
    lines = ["-DCOCOTB_SIM=1", "--top-module", TOP, *BUILD_ARGS]
    lines += [f"-D{key}={value}" for key, value in defines.items()]
    lines += [f"-I{path}" for path in includes]
    lines += [f"-GBAR0_RELOCATE={int(bar_relocate)}", *files]
    return "".join(f"{line}\n" for line in lines).encode()


def _input_fingerprints(files, includes):
    def checked(value):
        path = Path(value)
        # The immutable upstream Cocotb model entry is this one pinned link.
        # Check its indirection on both passes and hash the regular target;
        # other compiler inputs and include directories may not be links.
        model = ROOT / ".tools/verilog_pcie/tb/pcie_axi_master/pcie_if.py"
        if path == model:
            if (not path.is_symlink() or os.readlink(path) != "../pcie_if.py"
                    or path.resolve(strict=True) != model.parent.parent / "pcie_if.py"):
                raise ValueError("pinned PCIe Cocotb model link changed")
        elif path.is_symlink():
            raise ValueError(f"symlink in selected PCIe input: {path}")
        path = path.resolve(strict=True)
        if not path.is_relative_to(ROOT):
            raise ValueError(f"selected PCIe input outside checkout: {path}")
        return path

    headers = []
    for name in includes:
        directory = checked(name)
        if not directory.is_dir():
            raise ValueError(f"invalid PCIe include directory: {directory}")
        headers.extend(p for p in sorted(directory.rglob("*"))
                       if p.suffix in (".svh", ".vh"))
    files = dict.fromkeys(checked(path) for path in [*files, *headers])
    return {path.relative_to(ROOT).as_posix(): sha(path.read_bytes()) for path in files}


def _source_state():
    def git(*args):
        return subprocess.check_output(["git", *args], cwd=ROOT, text=True).strip()
    return git("rev-parse", "HEAD"), bool(git("status", "--porcelain"))


def _write_json(path, value):
    with path.open("x") as out:
        json.dump(value, out, indent=2)
        out.write("\n")


def run(*, bar_relocate: bool = False):
    pin = source_contract()
    target, plan = selected_plan(bar_relocate)
    commit, dirty = _source_state()
    if os.environ.get("GITHUB_RUN_ID") and (dirty or not os.environ.get("GITHUB_RUN_ATTEMPT")):
        raise ValueError("PCIe NoC CI requires clean source and exact attempt metadata")
    run_id = selected(target, plan, root=ROOT)["run_id"]
    private = ROOT / ".tools/pcie0/noc-builds"
    if any(path.is_symlink() for path in (private, private.parent, private.parent.parent)):
        raise ValueError("symlink in private PCIe build workspace")
    build = private / run_id
    build.mkdir(parents=True, exist_ok=False)
    patched = assert_iverilog_clean(output=build / "normalized/pcie_axi_master.v",
                                    probe=build / "pcie_bridge_check.vvp")
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
    compiler_inputs = _selected_filelist(files, includes, defs, bar_relocate)
    inputs = files + [str(ROOT / "gen/noc/floonoc/manifest.json"),
                      str(ROOT / "config/regression.yaml"),
                      str(ROOT / "dv/pcie0/upstream.lock.json"),
                      str(ROOT / "dv/pcie0/noc_smoke.py"),
                      str(ROOT / "dv/pcie0/discovery.py"),
                      *[str(vendor / p) for p in pin["python_models"]]]
    fingerprints = _input_fingerprints(inputs, includes)
    identity = selected(target, plan, root=ROOT, run_id=run_id, filelist_bytes=compiler_inputs)
    output = reserve_run(ROOT / ".tools/runs", identity, plan=plan)
    with (output / "sources.f").open("xb") as filelist:
        filelist.write(compiler_inputs)
    _write_json(output / "plan.json", {**plan, "identity": identity})
    with (output / "source-head.txt").open("x") as provenance:
        provenance.write(commit + "\n")
    _write_json(output / "pcie-noc-inputs.json",
                {"identity_sha256": identity["identity_sha256"], "commit": commit,
                 "dirty": dirty, "sha256": fingerprints,
                 "scope": "isolated_native_cocotb_no_passive_protocol_capture"})
    if path := os.environ.get("GITHUB_OUTPUT"):
        mode = "relocated" if bar_relocate else "legacy"
        with Path(path).open("a") as out:
            print(f"{mode}_canonical_id={relative_path(identity).as_posix()}", file=out)

    simulator = get_runner("verilator")
    # Compile generated package before its NoC module.
    assert files.index(generated[0]) < files.index(generated[1])
    try:
        simulator.build(
            sources=files, includes=includes, defines=defs,
            hdl_toplevel=TOP, build_dir=build / "obj",
            parameters={"BAR0_RELOCATE": int(bar_relocate)},
            build_args=list(BUILD_ARGS),
            always=True, waves=False, log_file=output / "build.log"
        )
    except Exception:
        diagnostic = output / "build.log"
        if diagnostic.exists():
            lines = diagnostic.read_text(errors="replace").splitlines()
            errors = [line for line in lines if line.startswith(("%Error", "%Warning"))]
            print("PCIe NoC build diagnostics:", *(errors[:60] or lines[-60:]), sep="\n", file=sys.stderr, flush=True)
        raise
    # A $fatal or assertion in Verilator terminates with SIGABRT before
    # Cocotb can write results.xml. Preserve and surface the actual
    # simulator stderr/log rather than an unhelpful generic exit -6.
    try:
        result = simulator.test(
            hdl_toplevel=TOP, hdl_toplevel_lang="verilog",
            test_module=MODULE, test_dir=ROOT / "dv/pcie0",
            results_xml=str(output / "results.xml"),
            log_file=output / "simulation.log",
        )
    except Exception:
        transcript = output / "simulation.log"
        if transcript.is_file():
            lines = transcript.read_text(errors="replace").splitlines()
            print(f"PCIe {'relocated' if bar_relocate else 'legacy'} "
                  "NoC RTL simulator aborted; last actual simulator lines:",
                  *lines[-100:], sep="\n", file=sys.stderr, flush=True)
        else:
            print("PCIe NoC RTL simulator aborted before writing simulation.log",
                  file=sys.stderr, flush=True)
        raise
    if Path(result) != output / "results.xml" or not Path(result).is_file():
        transcript = output / "simulation.log"
        details = transcript.read_text(errors="replace") if transcript.exists() else "(no simulation log)"
        print("PCIe real NoC/SRAM simulator failed before writing results XML:",
              details[-12000:], sep="\n", file=sys.stderr, flush=True)
        raise RuntimeError("missing Cocotb results XML: see simulator log above")
    xml = ElementTree.parse(result).getroot()
    tests = xml.findall(".//testcase")
    failures = [(t.get("name", "<unnamed>"), tag, t.find(tag))
                for t in tests for tag in ("failure", "error", "skipped")
                if t.find(tag) is not None]
    if (xml.tag not in ("testsuite", "testsuites")
            or [(test.get("classname"), test.get("name")) for test in tests] != [(MODULE, CASE)]
            or failures or any(node.get(key) not in (None, "0")
                               for node in xml.iter() for key in ("errors", "failures", "skipped"))):
        print(f"PCIe {'relocated' if bar_relocate else 'legacy'} NoC RTL "
              f"simulation failed: {len(tests)} testcases, {len(failures)} failures",
              file=sys.stderr, flush=True)
        for name, tag, node in failures:
            print(f"  {name}: {tag}: {node.get('message', '')}",
                  (node.text or "")[-5000:], sep="\n", file=sys.stderr, flush=True)
        transcript = output / "simulation.log"
        if transcript.is_file():
            print("Last simulator transcript lines:",
                  *transcript.read_text(errors="replace").splitlines()[-65:],
                  sep="\n", file=sys.stderr, flush=True)
        raise RuntimeError("real NoC/SRAM regression failed")
    verify_artifact_inventory(output, identity, [
        "plan.json", "sources.f", "source-head.txt", "pcie-noc-inputs.json",
        "build.log", "simulation.log", "results.xml",
    ], plan=plan)
    if (output / "sources.f").read_bytes() != compiler_inputs or (
            _input_fingerprints(inputs, includes) != fingerprints
            or _source_state() != (commit, dirty)):
        raise ValueError("PCIe NoC selected source changed during execution")
    mode_sample = f"PCIE0_RTL_BAR_RELOCATE_SAMPLED={int(bar_relocate)} after actual clock evaluation"
    if mode_sample not in (output / "simulation.log").read_text(errors="replace"):
        raise ValueError("original PCIe NoC simulation never observed the selected BAR mode")
    # The untouched native evidence remains workflow status, not a fabricated
    # result.json or a source-calibrated passive protocol capture.
    print("PCIE0_BAR_RELOCATED_NOC_SRAM_PASS" if bar_relocate
          else "PCIE0_REAL_NOC_SRAM_REGRESSION_PASS")


if __name__ == "__main__":
    run(bar_relocate=False)  # preserve established fast TLP-only mode
    run(bar_relocate=True)   # independent host-BAR->FlooNoC byte proof
