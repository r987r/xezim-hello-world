# Three-region Ethernet / CPU+DDR / PCIe chip

Configuration: `config/projects/ethernet-cpu-ddr-pcie/soc.yaml`
Project ID: `xezim_ethernet_cpu_ddr_pcie`.

This is a different project on the shared SoC infrastructure, not a
replacement for the original five-subsystem chip. It uses one PicoRV32
CPU with SRAM and PULP iDMA, a DDR-only memory subsystem, Ethernet0,
and PCIe0. No SERV, no HBM, no global **data** mesh.

## Physical-region view

```text
  Ethernet0 local data NoC       Compute0 local NoC         PCIe0 local NoC
       packet DMA ----- L0 -----> CPU / SRAM ------ L1 -----> PCIe bridge
                 \\
                  \\ independent DDR egress (address decoded)
                   \\-----> Memory0 local NoC -----> DDR0
                            ^
                            |
                Compute0 <--+-- central compute/memory link

      Global config FlooNoC: bottom, reaches all four subsystems
```

There are **four logical subsystems** in three physical regions.
The data links are bidirectional 1:1 AXI4 FlooNoCs:
Ethernet0–Compute0, **Ethernet0–Memory0**, Compute0–Memory0 and
Compute0–PCIe0. The Ethernet-local FlooNoC has two separate address-decoded
egresses for its traffic: `to_compute0` handles CPU/SRAM and reachable PCIe
ranges, and `to_memory0` handles the DDR range. AXI DDR writes do not
traverse the Compute0 local NoC or require CPU payload forwarding.
The shared route builder selects the shortest available physical path to a
target owner for all subsystems; optional placement hints affect the diagram,
not routing.

Each bidirectional link is implemented by two independent AXI initiator
directions, for eight directed FlooNoC networks and **17 total NoC instances**
in this configuration. The local DDR target still uses the memory subsystem's
selected controller/model. Project B's CPU cold-boot simulation passes;
its routed AXI payload traffic and live Ethernet/PCIe/DDR paths are not
qualified by that smoke test.

## Current generated and compiled boundary

The shared `tools/floonoc_gen.py`,
`tools/supernoc_gen.py`,
`tools/full_chip_gen.py`, and
`tools/chip_bootgen.py` support this structural project:
one CPU, DDR-only profile and real bidirectional direct data NoCs.
No second reset-release CSR is used. The existing generated default
tree is byte-for-byte unchanged.

Two independent project compile and real CPU cold-boot jobs have passed:
FlooGen/source selection, deterministic regeneration, Bender-pinned
RTL closure, Verilator elaboration, `--cc --build` C++ model compilation,
and execution of each project's own full-chip RTL checker. Project B's real
PicoRV32 boots and completes INIT/RUN/CHECK; Project A's two cores do likewise.
See [run 44139473560](https://github.com/r987r/xezim-hello-world/actions/runs/44139473560). See the [compile workflow](https://github.com/r987r/xezim-hello-world/actions/workflows/project-compile.yml).
The selected top `chip/soc_top.sv`, network wrapper
`supernoc/soc_noc.sv`, manifests, and complete
`chip/sources.f` are attached to that workflow's
`project-compile-xezim_ethernet_cpu_ddr_pcie-<run_id>` artifact,
or found in a local `.tools/projects/xezim_ethernet_cpu_ddr_pcie/` build.
They are not checked in under the canonical `gen/` tree.

## Not yet hardware-qualified

Compilation and CPU cold-boot simulation are **not** a routed protocol/data
qualification. In the compiled default-flavor top, selected Ethernet/PCIe
endpoint logic may remain reserved or idle; the full real Ethernet RX, DDR controller and
PCIe requester paths have not been exercised together. No Project B
end-to-end accepted AXI/TLP/GMII packet, DDR contents check or
byte-integrity PASS is claimed. Original Project A tests cannot
qualify Project B. Direct DDR-source PCIe DMA (without local SRAM
staging) is also a separate functional hardware requirement.

Outstanding existing acceptance is tracked in
[issue #255](https://github.com/r987r/xezim-hello-world/issues/255)
and [issue #167](https://github.com/r987r/xezim-hello-world/issues/167).
Those functional requirements remain open; they are not additional features
implied by the CPU boot-smoke milestone.

Command examples and project source file navigation are in
[multi-project Pages](multi-project-pages.md).
