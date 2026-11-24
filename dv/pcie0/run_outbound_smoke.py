"""Isolated *real RTL* outbound PCIe requester smoke, not a second SoC runner.

The already-pinned verilog-pcie dma_if_pcie is clocked against the same modeled
Root Complex used by PCIe0.  Its segmented RAM port is modeled locally here;
a separate SoC/iDMA-to-segmented-RAM adapter remains to be implemented under #76.
"""
import json
import os
from pathlib import Path
import subprocess
import sys
from xml.etree import ElementTree

ROOT = Path(__file__).resolve().parents[2]
VENDOR = ROOT / ".tools/verilog_pcie"
HERE = Path(__file__).resolve().parent
sys.path[:0] = [str(HERE), str(ROOT / "tools")]
from run_rtl_smoke import source_contract
from run_workspace import reserve_run, verify_artifact_inventory
from test_identity import relative_path, selected, sha


TOP = "dma_if_pcie"
MODULE = "outbound_smoke"
CASE = "outbound_bidirectional_real_tlps"
TIMESCALE = "1ns/1ps"
SCOREBOARD = "outbound-result.json"
MODEL_LINKS = {
    "tb/pcie_axi_master/pcie_if.py": "../pcie_if.py",
    "tb/dma_if_pcie_wr/dma_psdp_ram.py": "../dma_psdp_ram.py",
}


def source_state():
    def git(*args):
        return subprocess.check_output(["git", *args], cwd=ROOT, text=True).strip()
    return git("rev-parse", "HEAD"), bool(git("status", "--porcelain"))


def input_hashes(sources):
    files = [*map(Path, sources), HERE / f"{MODULE}.py", HERE / "upstream.lock.json"]
    for link, expected in MODEL_LINKS.items():
        path = VENDOR / link
        target = path.parent.parent / Path(expected).name
        if (not path.is_symlink() or os.readlink(path) != expected
                or path.resolve(strict=True) != target):
            raise ValueError(f"pinned outbound PCIe model link changed: {link}")
        files.append(target)
    output = {}
    for path in files:
        if path.is_symlink() or not path.resolve(strict=True).is_relative_to(ROOT):
            raise ValueError(f"unsafe outbound PCIe selected input: {path}")
        output[path.relative_to(ROOT).as_posix()] = sha(path.read_bytes())
    return output


def write_json(path, data):
    with path.open("x") as out:
        out.write(json.dumps(data, indent=2) + "\n")


def retain_native(build, output):
    # Preserve original Cocotb XML and timescale, including partial evidence on
    # a failure, without importing any private executable or waveform.
    xml = sorted(build.glob("*_results.xml"))
    if len(xml) > 1:
        raise ValueError("multiple native outbound PCIe XML results in one run")
    files = [(build / "timescale.f", "timescale.f")]
    if xml:
        files.append((xml[0], "results.xml"))
    files.extend((native, native.name) for native in sorted(build.glob("*.log")))
    for original, label in files:
        if original.is_symlink():
            raise ValueError(f"unsafe native outbound PCIe artifact: {original}")
        if original.is_file():
            with (output / label).open("xb") as out:
                out.write(original.read_bytes())


def check_native_xml(path):
    report = ElementTree.parse(path).getroot()
    cases = [(test.get("classname"), test.get("name")) for test in report.iter("testcase")]
    if (report.tag not in ("testsuite", "testsuites") or cases != [(MODULE, CASE)]
            or any(next(report.iter(tag), None) is not None for tag in ("failure", "error", "skipped"))
            or any(node.get(key) not in (None, "0") for node in report.iter()
                   for key in ("failures", "errors", "skipped"))):
        raise ValueError("original Icarus Cocotb XML does not match the passing outbound case")


def run():
    from cocotb_test.simulator import run as cocotb_run

    pin = source_contract()
    expected = [
        "rtl/dma_if_pcie.v",
        "rtl/dma_if_pcie_rd.v",
        "rtl/dma_if_pcie_wr.v",
        "rtl/priority_encoder.v",
        "rtl/pulse_merge.v",
    ]
    if pin.get("outbound_rtl_modules") != expected:
        raise RuntimeError("outbound PCIe RTL must use the reviewed pinned module list")
    if pin.get("outbound_python_models") != ["tb/dma_if_pcie_wr/dma_psdp_ram.py"]:
        raise RuntimeError("outbound PCIe RAM model must be pinned")

    if os.environ.get("SIM", "icarus") != "icarus" or os.environ.get("COCOTB_RESULTS_FILE"):
        raise ValueError("outbound PCIe requires Icarus and native run-owned XML")
    commit, dirty = source_state()
    if os.environ.get("GITHUB_RUN_ID") and (dirty or not os.environ.get("GITHUB_RUN_ATTEMPT")):
        raise ValueError("outbound PCIe CI requires clean source and exact attempt metadata")
    sources = [str(VENDOR / f) for f in expected]
    parameters = {
        "TLP_DATA_WIDTH": 64,
        "TLP_STRB_WIDTH": 2,
        "TLP_HDR_WIDTH": 128,
        "TLP_SEG_COUNT": 1,
        "RAM_SEL_WIDTH": 2,
        "RAM_ADDR_WIDTH": 16,
        "PCIE_TAG_COUNT": 32,
        "READ_OP_TABLE_SIZE": 8,
        "WRITE_OP_TABLE_SIZE": 8,
        "READ_TX_LIMIT": 4,
        "WRITE_TX_LIMIT": 4,
        "TX_SEQ_NUM_ENABLE": 0,
        "LEN_WIDTH": 16,
        "TAG_WIDTH": 8,
    }
    target = "pcie0-outbound-requester"
    plan = {"target": target, "engine": "cocotb-icarus", "sources": "pcie-outbound-isolated",
            "top": TOP, "module": MODULE, "logical_test": "outbound-host-memory-roundtrip",
            "parameters": parameters, "timescale": TIMESCALE}
    fingerprints = input_hashes(sources)
    preliminary = selected(target, plan, root=ROOT)
    private = ROOT / ".tools/pcie0/outbound-builds"
    if any(p.is_symlink() for p in (private, private.parent, private.parent.parent)):
        raise ValueError("symlink in private outbound PCIe build path")
    build = private / preliminary["run_id"]
    build.mkdir(parents=True, exist_ok=False)
    # Mirror the existing Cocotb-test Icarus compile options (excluding only
    # its generated simulator output path) with no changes to the invocation.
    args = ["-D", "COCOTB_SIM=1", "-g2012", "-s", TOP,
            *(f"-P{TOP}.{k}={v}" for k, v in parameters.items()),
            "-f", str(build / "timescale.f"), *sources]
    filelist = "".join(f"{arg}\n" for arg in args).encode()
    identity = selected(target, plan, root=ROOT, run_id=preliminary["run_id"],
                        filelist_bytes=filelist)
    output = reserve_run(ROOT / ".tools/runs", identity, plan=plan)
    (output / "sources.f").write_bytes(filelist)
    write_json(output / "plan.json", {**plan, "identity": identity})
    (output / "source-head.txt").write_text(commit + "\n")
    write_json(output / "outbound-inputs.json", {
        "identity_sha256": identity["identity_sha256"], "commit": commit, "dirty": dirty,
        "sha256": fingerprints, "scope": "isolated_native_scoreboard_no_passive_report",
    })
    write_json(output / "rtl-sources.json", {
        "upstream_sha": pin["commit"],
        "module": TOP,
        "rtl": expected,
        "parameters": parameters,
        "boundary": "isolated segmented device RAM; NOT iDMA or generated FlooNoC",
    })
    if path := os.environ.get("GITHUB_OUTPUT"):
        with Path(path).open("a") as out:
            print(f"archive_dir=.tools/runs/{relative_path(identity).as_posix()}/", file=out)

    # Native scoreboard bytes are retained directly, but this is not the
    # shared publisher's result.json schema and cannot qualify a report.
    result = output / SCOREBOARD
    try:
        native = cocotb_run(
            verilog_sources=sources,
            toplevel=TOP,
            module=MODULE,
            python_search=[str(HERE), str(VENDOR / "tb/pcie_axi_master"),
                           str(VENDOR / "tb/dma_if_pcie_wr")],
            parameters=parameters,
            sim_build=str(build),
            extra_env={"SOC_PCIE_OUTBOUND_RESULT": str(result)},
            timescale=TIMESCALE,
        )
    finally:
        retain_native(build, output)
    xml_file = Path(native)
    if (xml_file.parent != build or not xml_file.name.endswith("_results.xml")
            or not xml_file.is_file() or xml_file.is_symlink()):
        raise ValueError("outbound PCIe simulator returned foreign results XML")
    verify_artifact_inventory(output, identity, ["sources.f", "plan.json", "source-head.txt",
        "outbound-inputs.json", "rtl-sources.json", "results.xml", "timescale.f", SCOREBOARD], plan=plan)
    if ((output / "timescale.f").read_bytes() != f"+timescale+{TIMESCALE}\n".encode()
            or (output / "sources.f").read_bytes() != filelist
            or input_hashes(sources) != fingerprints or source_state() != (commit, dirty)):
        raise ValueError("outbound PCIe selected inputs changed during execution")
    check_native_xml(output / "results.xml")
    evidence = json.loads(result.read_text())
    if not evidence.get("passed") or not all(evidence.get(k, 0) > 0 for k in
                                          ("tx_mem_write_tlps", "tx_mem_read_tlps",
                                           "rx_completion_tlps", "host_bytes_verified",
                                           "device_bytes_verified")):
        raise RuntimeError("outbound requester lacks positive TLP/byte evidence")
    print("PASS PCIE0_OUTBOUND_REQUESTER_REAL_TLP:", json.dumps(evidence, sort_keys=True))


if __name__ == "__main__":
    run()
