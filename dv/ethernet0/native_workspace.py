"""Archive existing isolated Icarus/Cocotb runs without claiming passive traffic."""
from __future__ import annotations

from collections import Counter
import json
import os
from pathlib import Path
import subprocess
from xml.etree import ElementTree

from tools.run_workspace import reserve_run, verify_artifact_inventory
from tools.test_identity import selected, sha

ROOT = Path(__file__).resolve().parents[2]
PROFILES = {
    "ethernet0-gmii": (
        "ethernet0_mac_gmii", "dv.ethernet0.tb_mac_gmii", "mac-gmii-rx-tx", (
            "rx_and_tx_over_real_gmii_mac_and_async_fifos",
            "corrupted_fcs_is_detected_and_not_delivered",
            "sustained_1gbe_rx_and_tx_without_width_bottleneck",
            "rx_backpressure_drops_whole_frames_without_partial_delivery",
        ),
    ),
    "ethernet0-gmii-stage": (
        "ethernet0_rx_gmii_stager", "dv.ethernet0.tb_gmii_frame_stager", "gmii-frame-staging", (
            "gmii_to_metadata_and_preserved_ethernet_bytes",
            "gmii_bad_fcs_never_becomes_policy_metadata",
        ),
    ),
    "ethernet0-mvp-rx": (
        "ethernet0_rx_mvp_tb", "dv.ethernet0.tb_rx_mvp", "gmii-rx-to-sram",
        ("real_gmii_rx_and_b_gated_cq",),
    ),
    "ethernet0-mvp-tx": (
        "ethernet0_tx_mvp_tb", "dv.ethernet0.tb_tx_mvp", "sram-to-gmii-tx",
        ("tx_descriptor_through_real_gmii_and_cq",),
    ),
}


def validate_xunit(data: bytes, module: str, expected: tuple[str, ...]) -> None:
    xml = ElementTree.fromstring(data)
    cases = [(case.get("classname"), case.get("name")) for case in xml.iter("testcase")]
    if (xml.tag not in ("testsuite", "testsuites")
            or Counter(cases) != Counter((module, name) for name in expected)
            or any(next(xml.iter(tag), None) is not None for tag in ("failure", "error", "skipped"))
            or any(node.get(key) not in (None, "0")
                   for node in xml.iter() for key in ("failures", "errors", "skipped"))):
        raise ValueError("original Icarus Cocotb XML does not match the exact passing case set")


def _fingerprints(root: Path, paths: list[Path]) -> list[dict]:
    result = []
    for source in paths:
        if not source.is_file() or source.is_symlink() or not source.resolve().is_relative_to(root):
            raise ValueError(f"missing or unsafe Icarus selected input: {source}")
        raw = source.read_bytes()
        result.append({"path": source.relative_to(root).as_posix(), "bytes": len(raw), "sha256": sha(raw)})
    return result


def _source_state(root: Path) -> tuple[str, bool]:
    def git(*args):
        return subprocess.check_output(["git", *args], cwd=root, text=True).strip()

    return git("rev-parse", "HEAD"), bool(git("status", "--porcelain"))


def run_existing_icarus(target: str, sources: list[Path], *, extra_env=None) -> Path:
    """Run the original RTL/VIP and keep only selectable, native run evidence."""
    from cocotb_test.simulator import run

    top, module, logical_test, expected = PROFILES[target]
    sources = [Path(source).absolute() for source in sources]
    if not sources:
        raise ValueError("isolated Ethernet Icarus sources are empty")
    inputs = sources + [ROOT / "rtl/io/ethernet0/ip.lock.yml",
                        ROOT / "config/ip.lock.yaml",
                        ROOT / (module.replace(".", "/") + ".py")]
    fingerprints = _fingerprints(ROOT, inputs)
    commit, dirty = _source_state(ROOT)
    if os.environ.get("GITHUB_RUN_ID") and (dirty or not os.environ.get("GITHUB_RUN_ATTEMPT")):
        raise ValueError("Icarus CI requires clean source and exact attempt metadata")
    filelist = "".join(f"{source}\n" for source in sources).encode()
    plan = {"target": target, "sources": "ethernet-standalone", "top": top, "module": module,
            "engine": "cocotb-icarus", "logical_test": logical_test, "timescale": "1ns/1ps"}
    identity = selected(target, plan, filelist_bytes=filelist, root=ROOT)
    directory = reserve_run(ROOT / ".tools/runs", identity, plan=plan)
    plan["identity"] = identity
    with (directory / "sources.f").open("xb") as out:
        out.write(filelist)
    with (directory / "plan.json").open("x") as out:
        out.write(json.dumps(plan, indent=2) + "\n")
    with (directory / "source-head.txt").open("x") as out:
        out.write(commit + "\n")
    with (directory / "icarus-inputs.json").open("x") as out:
        out.write(json.dumps({"identity_sha256": identity["identity_sha256"], "commit": commit,
                              "dirty": dirty, "files": fingerprints,
                              "scope": "isolated_native_cocotb_no_passive_protocol_capture"}, indent=2) + "\n")
    print("Isolated Ethernet run workspace:", directory, flush=True)
    if path := os.environ.get("GITHUB_OUTPUT"):
        with Path(path).open("a") as out:
            print(f"{target.replace('-', '_')}_run_id={identity['run_id']}", file=out)
    build_root = ROOT / ".tools/ethernet-icarus-builds"
    if build_root.is_symlink():
        raise ValueError("Ethernet private Icarus build root cannot be a symlink")
    build = build_root / identity["run_id"]
    build.mkdir(parents=True, exist_ok=False)
    options = {} if extra_env is None else {"extra_env": extra_env}
    try:
        run(simulator="icarus", verilog_sources=[str(p) for p in sources],
            toplevel=top, module=module, python_search=[str(ROOT)], sim_build=str(build),
            timescale=plan["timescale"], waves=False, **options)
    finally:
        # If Cocotb fails, keep any original XML already emitted for diagnosis.
        xml = list(build.glob("*_results.xml"))
        timescale = build / "timescale.f"
        for native, label in ((xml[0] if len(xml) == 1 else None, "results.xml"),
                              (timescale, "timescale.f")):
            if native is not None and native.is_file() and not native.is_symlink():
                with (directory / label).open("xb") as out:
                    out.write(native.read_bytes())
    if _fingerprints(ROOT, inputs) != fingerprints or _source_state(ROOT) != (commit, dirty):
        raise ValueError("Icarus selected source changed during native execution")
    verify_artifact_inventory(directory, identity, [
        "sources.f", "plan.json", "source-head.txt", "icarus-inputs.json", "results.xml", "timescale.f",
    ], plan=plan)
    if (directory / "timescale.f").read_bytes() != b"+timescale+1ns/1ps\n":
        raise ValueError("original Icarus timescale differs from the selected invocation")
    validate_xunit((directory / "results.xml").read_bytes(), module, expected)
    # No result.json/protocol JSON: the current Pages reader only publishes
    # workflow status for these isolated testbench scopes.
    return directory
