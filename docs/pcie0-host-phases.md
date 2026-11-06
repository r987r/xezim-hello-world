# PCIe0: host participant in the existing INIT/RUN/CHECK framework

This implementation was merged in [PR #60](https://github.com/r987r/xezim-hello-world/pull/60),
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
| RUN | CPU0 executes real C/iDMA copies between PCIe SRAM and modeled DDR before notifying host; CPU1 participates in hello/peer checks | Wait for RUN permission, read 64 DMA-returned bytes at BAR0+0x600 and verify; also check four distinct BAR write/read vectors; ACK RUN | CPU iDMA descriptors/IRQ, completed AXI/DDR-model writes, TLP completion data and independent payload checks |
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

The combined PCIe-host and separate CPU C/iDMA tests use the same ABI via
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

## Minimum DDR-model ↔ PCIe host functional integration — VERIFIED RTL

The **single** `chip-pcie-host` test selects firmware mode
`pcie_dma_host`. The actual connected path uses PicoRV32 CPU0 executing
RV32I C, upstream PULP iDMA, independent generated data/config FlooNoCs,
a real `pcie_axi_master` TLP-to-AXI bridge, PULP SRAM, and a modeled
`cocotbext-pcie` Root Complex/link. The configured DDR window is a
**64-KiB behavioral AXI memory model, not a LiteDRAM controller or physical
DDR PHY**. The normal CPU/DMA and full-chip boot profiles remain separate.

[Exact-head PCIe CI run 42134213227](https://github.com/r987r/xezim-hello-world/actions/runs/42134213227)
passed both jobs. The `chip-pcie-host` simulation completed 27
INIT/RUN/CHECK steps with zero flow issues, 47,864 complete AXI transactions
and no outstanding transactions, and independently correlated 3,741 PCIe
read TLPs to 3,741 completion TLPs, plus 8 accepted posted writes.
The generated `traffic-latency.json` reports no mismatches and a measured
TLP request-to-completion mean of **130.083 ns**, min 130 ns, max 200 ns,
at the recorded 10 ns clock. The four explicit host BAR read callbacks
measured 170/220/310/260 ns. Those host API spans use a *modeled*
Root Complex; physical PCIe link/host latency is not measured.
Source run SHA in the artifact is a GitHub PR merge-test commit
(`2b10ba60912190ff705e2a39cc186c583cce7dd7`),
descended from PR head `1559c3348d5196984b9eeb5d73f9a36c2563b8e1`.

### Data movement and checks

| Phase | Real hardware actions | Independent evidence |
| --- | --- | --- |
| INIT | Host writes 64 known bytes through BAR0 to PCIe SRAM `+0x500`, reads them back, then ACKs CPU0 | Actual accepted ingress TLPs, bridge AXI completions and SRAM byte comparison |
| RUN: host → DDR | CPU0 programs real iDMA: PCIe SRAM `+0x500` → modeled DDR `+0x800`. A second DMA submission later copies DDR `+0x800` → CPU-visible SRAM | Completed DMA AXI read/write, DDR model target writes/reads, C verification of all 64 host bytes |
| RUN: DDR → host | CPU0 initializes SRAM bytes and iDMA writes a separate DDR buffer, then iDMA copies DDR → PCIe SRAM `+0x600`; host reads BAR0 `+0x600` | Actual DMA AXI read/write, SRAM target response, PCIe completion TLP, host comparison of all 64 bytes |
| CHECK | Host/CPU acknowledgements, CPU peer checks and final PASS | One shared `test-flow.json` and full AXI/TLP transaction report |

This is **two short real iDMA submissions, two independent descriptors
each**. The comprehensive DDR/HBM and dual-engine/interrupt tests remain
in their own regressions; no duplicate DMA engine, PCIe VIP, or test runner
was added. `test-flow.json` includes `host0.seed_ddr_input`,
`cpu0.pcie_ddr_exchange`, and `host0.read_ddr_dma_output`.

The PCIe result in this document explicitly uses **modeled DDR**. A
separate opt-in CPU/iDMA→real LiteDRAM controller path now passes
[DDR-B CI #42217902632](https://github.com/r987r/xezim-hello-world/actions/runs/42217902632), but that is **not** evidence
of PCIe host transactions using the real controller. The combined
PCIe+real-DDR path remains an epic #34 interoperability gate.

### Not part of initial PCIe closure

- The host **pulls** DDR data by BAR read; there is **no** endpoint-initiated
  outbound PCIe write into Root Complex host RAM. This requires an outbound
  PCIe requester path and its own test.
- Actual Ethernet MAC/queue/GMII-to-NoC attachment remains the Ethernet
  integration track; it is not proven by PCIe+DDR smoke alone.
- Physical PCIe PHY/PIPE/LTSSM, MSI/MSI-X, independent PCIe CSR
  implementation, multiple outstanding tags, backpressure, error/recovery,
  performance/stress and real DDR4/DFI qualification remain separate.
- In opt-in generated `manifest.json`, PCIe RTL is marked live;
  unconnected Ethernet endpoints are labeled reserved, not promoted
  based on this simulation.

### Reproduction and results

Run `python3 tools/regress.py chip-pcie-host` (requires pinned PCIe/iDMA
dependencies and the RV32I compiler) or use the
[PCIe0 integrated workflow](../.github/workflows/pcie0-integrated.yml).
Inspect `result.json`, `test-flow.json`, `axi-transactions.json`,
`protocol-transactions.json`, `traffic-latency.json`,
`report.html`, `protocols.html` and `test-flow.html` in the
[successful CI artifact](https://github.com/r987r/xezim-hello-world/actions/runs/42134213227).

The *independent* SuperNoC structure/traffic test is a distinct CI job.
A later NoBResponseIdQueue assertion there must not be relabeled as a
PCIe traffic mismatch; follow that gate separately before claiming a
completely green repository-wide integration.
