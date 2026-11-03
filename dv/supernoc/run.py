"""Compile and run one eight-FlooNoC RTL test using cocotb + Verilator.

All third-party RTL comes from FlooNoC's pinned upstream Bender checkout.
BFMs come from open-source cocotbext-axi; no home-grown AXI VIP.
"""
import os
from pathlib import Path
import json
from xml.etree import ElementTree
from cocotb.runner import get_runner

ROOT=Path(__file__).resolve().parents[2]
os.chdir(ROOT)
noc=ROOT/"gen/noc/floonoc"
manifest=json.loads((noc/"manifest.json").read_text())["networks"]
source_list=ROOT/".tools/floonoc-lint.f"
assert source_list.is_file(), "Run the locked FlooNoC Bender checkout first"
packages=[noc/p["package"] for _,p in sorted(manifest.items())]
tops=[noc/p["top"] for _,p in sorted(manifest.items())]
include_paths=[
    ROOT/".tools/floonoc/hw/include",
    *(p for p in (ROOT/".tools/floonoc/.bender/git/checkouts").glob("*/include") if p.is_dir())
]
runner=get_runner("verilator")
if os.getenv("SUPERNOC_TEST_ONLY") == "1":
    # Reuse only an explicitly requested local build for Python-only DV edits.
    # The positive CI gate always compiles; its negative run reuses that DUT.
    runner.build_dir = ROOT / ".tools/supernoc-obj"
    assert (runner.build_dir / "supernoc_tb").is_file(), "Build the DUT first"
else:
    runner.build(
        sources=[*packages,*tops,ROOT/"gen/supernoc/supernoc_tb.sv"],
        includes=include_paths,
        build_args=["--timing","--assert","-Wno-fatal","-f",str(source_list)],
        hdl_toplevel="supernoc_tb",
        build_dir=ROOT/".tools/supernoc-obj",
        always=True,
        waves=False,
    )
results = runner.test(
    hdl_toplevel="supernoc_tb",
    hdl_toplevel_lang="verilog",
    test_module="test_supernoc",
    test_dir=ROOT/"dv/supernoc",
    results_xml=os.getenv("SUPERNOC_RESULTS_XML", "results.xml"),
)
tests = ElementTree.parse(results).findall(".//testcase")
if not tests or any(any(t.find(tag) is not None for tag in ("failure", "error", "skipped"))
                    for t in tests):
    raise SystemExit("supernoc cocotb regression failed; see results XML")
