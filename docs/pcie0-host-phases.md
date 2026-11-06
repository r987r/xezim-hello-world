# PCIe0: host participant in the existing INIT/RUN/CHECK framework

This implementation is tracked in [draft PR #60](https://github.com/r987r/xezim-hello-world/pull/60),
based directly on `main` (generator PR #53 already merged). It does **not** introduce another test runner,
phase engine, TestML parser, or duplicate full-chip testbench.

## Verification layers and evidence

- **Actual RTL:** pinned `pcie_axi_master` TLP→64-bit AXI4, independent
  generated `pcie0_local_data` and `pcie0_local_config` FlooNoCs,
  global data/config fabric, `axi_sram_target` and PULP `tc_sram`;
  real PicoRV32/SERV boot firmware. The PCIe controller CSR is still
  reserved and responds with AXI errors.
- **Behavioral host:** `cocotbext-pcie` Root Complex and endpoint link
  model; not a PHY, PIPE implementation, or real LTSSM.
- **Single test owner:** `dv/full_chip/test_boot.py::execute_cold_boot`
  controls *both* ordinary CPU tests and the PCIe0-host variant.
- **External adapter:** `dv/pcie0/host_adapter.py` implements
  enumeration, enabling BAR0, write/read/check, and acknowledgements.
  It cannot advance CPU phases independently. The compatibility
  selector `dv/pcie0/test_full_chip_host.py` merely invokes the shared
  entrypoint.
- **Execution:** `config/regression.yaml` test `chip-pcie-host`,
  through existing `tools/regress.py`/Verilator/Cocotb, the established
  generated SV checker, memory pattern model, passive AXI monitors,
  and unified run explorer.

## End-to-end stage and ownership

| Stage | CPU coordinator and other CPUs | PCIe0 host participant | Independent checker |
| --- | --- | --- | --- |
| INIT | CPU0 uses ROM/flash to start CPUs; CPU1 writes its ready mailbox; CPU0 emits `DEVICE_INIT_READY` to real remote PCIe0 SRAM over **Compute0 local → global data → PCIe0 local** | Root Complex enumerates and enables BAR0; observes ready by real BAR read, then writes host init acknowledgment | SV checker requires all CPU ready/config registers and emits actual RTL phase steps |
| RUN | CPU0 waits for host acknowledgment before publishing RUN. CPU1 participates in normal hello/peer checks | Read RUN permission; four distinct BAR writes and four independent readbacks with address-based golden patterns; records every operation; write host RUN acknowledgment | PULP SRAM accepted-read/write counters, AXI monitor and independent data comparison |
| CHECK | CPU0 waits for host check acknowledgment and final CPU peer checks | Waits for CHECK permission, writes acknowledgment through BAR, validates clean completion | CPU checker PASS, exact CPU masks, host markers, real SRAM path, and required-step report |

Handshake addresses and constants are derived from the generated variant
`firmware.json`, not manually preloaded into writable SRAM.
The host phase mailbox is at the configured PCIe0 SRAM base + `0x800`
for this test (currently `0x12000800`).

The previously observed real CPU0 DecodeError for `0x12000800`
came from compute-local FlooGen routes missing peripheral SRAM.
Shared PR #53 now generates remote destinations from **all**
compute/peripheral SRAM windows, with a fail-closed routing regression.
PR #60 incorporates that regenerated RTL.

The 512-byte CPU0 flash image is an opt-in variant under
`.tools/regression/chip-pcie-host/variant`; standard 256-byte
CPU boot and canonical checked-in `gen/` files are not overwritten.

## One step-report ABI for all sources

See [Canonical test-flow evidence](test-flow.md). Python host stimulus,
actual SV firmware stage markers, and optional C firmware MMIO markers
appear in one ordered `test-flow.json` and `test-flow.html`, linked
from the existing AXI `report.html`. Each step is declared under
`report.flow.required_steps` in **the same test YAML**.
Missing, unregistered, duplicate, corrupt, or failed expected steps fail CI.

The CPU C/iDMA test now uses the same ABI via
`sw/common/test_flow.h`, an isolated CPU0 mailbox marker word, and
the same AXI reporter. C statements are not considered RTL evidence
unless the AXI monitor observes completed OKAY writes.

Non-instrumented legacy tests show **UNMEASURED** step coverage rather
than incorrectly claiming every action was reported. This is an
incremental migration gate, not a promise that all existing test
drivers have already been instrumented.

## Reproduce and acceptance

```sh
python3 -m unittest tests.test_test_flow tests.test_test_flow_cross_source -v
python3 tools/regress.py chip-pcie-host
python3 tools/regress.py chip-cpu-dma
```

Use `.github/workflows/pcie0-integrated.yml` for exact-head pinning,
generated RTL drift checks, hosted RC smoke, and CPU C/iDMA phase tests.
The unified artifact contains original AXI/protocol traces, pass/fail
results, and the full step report.

**Still separate from this scope:** silicon PCIe PHY/link recovery,
upstream endpoint register RTL, outbound DMA to host memory, MSI/MSI-X,
and full multiple-outstanding-tag stress. A modeled host enumeration
is not a physical-link signoff.

## Minimal real DDR-model ↔ PCIe host integration (same regression)

`chip-pcie-host` now uses firmware mode `pcie_dma_host`. This is the
**smallest combined full-chip RTL**: real PicoRV32 CPU, real pinned PULP iDMA,
real NoC/crossbar/PCIe SRAM, real `pcie_axi_master` bridge and a modeled
Root Complex. DDR is still the named 64-KiB AXI-backed behavioral model,
**not** the separate isolated LiteDRAM controller.

INIT:
- Host enumerates BAR0, waits for CPU firmware ready, writes and reads back
  64 known bytes at PCIe SRAM +`0x500`, then acknowledges INIT.
- CPU0 does not preload this SRAM and does not run the C DMA before host
  acknowledgment.

RUN:
- CPU0 executes its **existing** C DMA allocation/DDR/HBM roundtrip and
  descriptor/IRQ checks, then three more real DMA descriptors:
  PCIe SRAM +`0x500` → modeled DDR +`0x800`;
  existing DMA-populated DDR region → PCIe SRAM +`0x600`;
  DDR +`0x800` → CPU-visible SRAM. The comprehensive DDR/HBM\n  five-descriptor test still runs independently as `chip-cpu-dma`.
- CPU0 checks the host's 64 bytes after the last descriptor, validates
  descriptors and IRQ, then announces RUN to the host.
- Host reads BAR0+`0x600`, independently checks every byte against the CPU
  source pattern, runs the original four independent BAR vectors, and ACKs.

CHECK:
- The unchanged CPU/host CHECK handshake runs after both directions pass.
  The passive AXI reporter validates accepted transfers/completions and the
  shared TLP observer validates the inbound host TLP/completion stream.
  The common `test-flow.json` adds `host0.seed_ddr_input`,\n  `cpu0.pcie_ddr_exchange`, and `host0.read_ddr_dma_output`.

The host uses BAR readback (a **host pull**), not a device-initiated PCIe
outbound memory-write TLP. Production host-memory DMA via upstream
`dma_if_pcie`, actual Ethernet ingress/egress, real DDR/DFI qualification,
multiple outstanding tags and backpressure/throughput are separate tracks.
The generated `manifest.json` marks the PCIe bridge as live only in this
opt-in variant; Ethernet remains reserved until actually attached.
