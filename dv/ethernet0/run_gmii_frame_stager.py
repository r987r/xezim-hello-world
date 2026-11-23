#!/usr/bin/env python3
"""Run real GMII MAC -> complete-frame and header-tap RTL with pinned IP."""
from pathlib import Path
import os
import subprocess
import sys

ROOT=Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0,str(ROOT))
from dv.ethernet0.run_mac_gmii import fetch_pinned

def main():
    upstream=fetch_pinned()
    files=[
        ROOT/"rtl/io/ethernet0/ethernet0_rx_gmii_stager.v",
        ROOT/"rtl/io/ethernet0/ethernet_rx_frame_stager.v",
        ROOT/"rtl/io/ethernet0/ethernet0_mac_gmii.v",
    ]
    for n in ("verilog_ethernet","verilog_axis"):
        directory,meta=upstream[n]
        files += [directory/p for p in meta["modules"]]
    subprocess.run(["iverilog","-g2012","-s","ethernet0_rx_gmii_stager",
                    "-t","null",*[str(f) for f in files]],check=True)
    print("PASS real Ethernet GMII frame frontend RTL elaboration",flush=True)
    from dv.ethernet0.native_workspace import run_existing_icarus

    os.chdir(ROOT)
    run_existing_icarus("ethernet0-gmii-stage", files)
    print("PASS real GMII->MAC->CDC->frame stage RTL and FCS negative",flush=True)

if __name__=="__main__":
    main()
