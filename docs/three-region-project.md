# Project B: Ethernet -- CPU/DDR -- PCIe

This is a second independent SoC project definition for issue #167 in the
existing r987r/xezim-hello-world repository. It does NOT modify the five-
subsystem default project, and is not yet an executable generated full chip.

## Topology

The three physical regions, left to right, are Ethernet0, CPU0+Memory0,
PCIe0. The center includes two logical reusable subsystems, Compute0 and
Memory0. The bottom global_config FlooNoC reaches all four subsystems.

Each neighboring pair uses two opposite AXI initiator directions, including
the normal AXI response channels: Ethernet0 <-> Compute0, Compute0 <->
Memory0, and Compute0 <-> PCIe0. There is no global data NoC, no HBM, no
second CPU, and no reset-release protocol.

## What the first branch slice actually establishes

- A second source project using schema_version 2 and existing IP IDs, memory
  map conventions, and interconnect backend names.
- Shared source validation of DDR-only, one-CPU, direct-link topology and
  full physical-region coverage, including deliberately invalid fixtures.
- One-CPU ROM-copy firmware generation without a phantom secondary release.
- Existing two-CPU global-data project remains the default; neither its RTL
  nor its generated graphics are replaced by this project configuration.

The memory subsystem can be unit-generated with one DDR ingress/one target
from the existing Verilog-AXI memory testbench. That is not proof of whole-
chip flow routing.

## Not yet implemented / do not report as verified

Current floonoc_gen.py, supernoc_gen.py, full_chip_gen.py and CPU0's
full-chip C boot emitter still assume the old global-data/two-core topology.
The current make gen command is for the default project ONLY.

Next: emit real FlooNoC direct links, wire selected Ethernet/CPU/DDR/PCIe
RTL, qualify exact-source AXI traffic and byte integrity, then add two-
project regression selection and existing GitHub Pages viewer design switch.
No extra simulator/test/scenario engine, protocol monitor or reporting site.

PCIe host transmission initially uses existing local-PCIe-SRAM staging.
Direct DDR-source PCIe requester access is a separate hardware requirement;
never claim zero-copy from a source-only topology drawing.

Focused source check: python3 -m unittest tests.test_three_region_project -v
This unit test does not elaborate or simulate whole-chip RTL.
