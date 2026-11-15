# Three-region Ethernet / CPU+DDR / PCIe chip

Configuration: `config/projects/ethernet-cpu-ddr-pcie/soc.yaml`
Project ID: `xezim_ethernet_cpu_ddr_pcie`.

This is a different project on the shared SoC infrastructure, not a
replacement for the original five-subsystem chip. It uses one PicoRV32
CPU with SRAM and PULP iDMA, a DDR-only memory subsystem, Ethernet0,
and PCIe0. No SERV, no HBM, no global **data** mesh.

## Physical-region view

```text
  Ethernet0          CPU0 + Memory0             PCIe0
  GMII / DMA   <-->   CPU / SRAM / DDR    <-->   PCIe bridge
           L0            central link         L1

      global_config FlooNoC on the bottom, reaches all four subsystems
```

There are **four logical subsystems** in three physical regions.
The data links are bidirectional 1:1 AXI4 FlooNoCs:
Ethernet0–Compute0, Compute0–Memory0 and Compute0–PCIe0.
Each link needs two separate AXI initiator directions and normal
read/write response channels. The source-selected emitter produces
six directed FlooNoC networks as part of 15 total NoC instances
in this configuration. The central compute fabric routes by address;
it does not imply CPU software copies every payload.

## Current generated and compiled boundary

The shared `tools/floonoc_gen.py`,
`tools/supernoc_gen.py`,
`tools/full_chip_gen.py`, and
`tools/chip_bootgen.py` support this structural project:
one CPU, DDR-only profile and real bidirectional direct data NoCs.
No second reset-release CSR is used. The existing generated default
tree is byte-for-byte unchanged.

Two independent project compile jobs have passed:
FlooGen/source selection, deterministic regeneration, Bender-pinned
RTL closure, Verilator elaboration, and `--cc --build` C++
model compilation. See the [compile workflow](https://github.com/r987r/xezim-hello-world/actions/workflows/project-compile.yml).
The selected top `chip/soc_top.sv`, network wrapper
`supernoc/soc_noc.sv`, manifests, and complete
`chip/sources.f` are attached to that workflow's
`project-compile-xezim_ethernet_cpu_ddr_pcie-<run_id>` artifact,
or found in a local `.tools/projects/xezim_ethernet_cpu_ddr_pcie/` build.
They are not checked in under the canonical `gen/` tree.

## Not yet hardware-qualified

Compilation is **not** a functional system test. In the compiled
default-flavor top, selected Ethernet/PCIe endpoint logic may remain
reserved or idle; the full real Ethernet RX, DDR controller and
PCIe requester paths have not been exercised together. No Project B
end-to-end accepted AXI/TLP/GMII packet, DDR contents check or
byte-integrity PASS is claimed. Original Project A tests cannot
qualify Project B. Direct DDR-source PCIe DMA (without local SRAM
staging) is also a separate functional hardware requirement.

Next implementation: enable Project B's selected real IP attachments,
add a separate exact-source regression target using the shared
INIT/RUN/CHECK and passive monitor infrastructure, and verify
Ethernet→CPU SRAM/DDR, DDR→PCIe and reverse host operations with real
completions and byte checks.

Command examples and project source file navigation are in
[multi-project Pages](multi-project-pages.md).
