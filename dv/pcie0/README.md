# PCIe0 real RTL bring-up

Tracked by [issue #36](https://github.com/r987r/xezim-hello-world/issues/36), [draft PR #51](https://github.com/r987r/xezim-hello-world/pull/51) and parent #34.

## Current status — dedicated PCIe0 and real full-chip DMA smoke

**Initial PCIe0 path verified in [PR #60](https://github.com/r987r/xezim-hello-world/pull/60)**:
[exact-head CI 42134213227](https://github.com/r987r/xezim-hello-world/actions/runs/42134213227)
passes a real PCIe TLP→AXI master attached to the **dedicated**
`pcie0_local_data` FlooNoC and PULP SRAM, with real CPU0/iDMA through
independent local/global NoCs and a **modeled DDR** target. Modeled host
BAR0 writes 64 bytes, CPU0 iDMA copies them PCIe SRAM→DDR→CPU SRAM,
and a separate 64-byte SRAM→DDR→PCIe SRAM transfer is pulled via host
BAR0 and compared. The same run checks 27 INIT/RUN/CHECK steps, 47,864
complete AXI transactions, 3,741 matched PCIe read/completion pairs,
8 posted writes and a measured PCIe read TLP mean of 130.083 ns.
Generated PCIe RTL is marked live in this variant; no physical PHY or
outbound DMA is claimed. See [shared full-chip PCIe scope](../../docs/pcie0-host-phases.md).

**The two stages below are historical isolated milestones**, not a
description of the current full-chip topology. The first isolated test
used `cocotbext-axi AxiRam`; the second temporarily reused
Compute0's mesh before the dedicated PCIe0 FlooNoC was generated.

## Verified simulation stages

**Stage 1 — real PCIe TLP-to-AXI4 bridge**

```
cocotbext-pcie RootComplex + PcieIfDevice (modeled link/Endpoint)
    -> pinned verilog-pcie pcie_axi_master RTL
    -> cocotbext-axi AxiRam memory model
```

Icarus and the upstream Cocotb 1.7.2 test profile: four independent PCIe BAR0 read/write vectors, byte strobes, unaligned payload and 4 KiB-boundary behavior. The upstream RTL has immutable MIT pin `25156a9a162c41c60f11f41590c7d006d015ae5a`. Build-time, fail-closed `prepare_rtl.py` corrects exactly four upstream demux unsized zero port tie-offs without modifying upstream checkout; an Icarus diagnostic is an explicit failure, **even if Cocotb reports PASS**.

**Stage 2 — real generated FlooNoC and SRAM, not AxiRam**

```
cocotbext-pcie modeled RootComplex + Endpoint
    -> real pcie_axi_master RTL
    -> actual generated compute0_local_data FlooNoC
    -> actual axi_sram_target RTL
    -> upstream PULP tc_sram RTL (0x10000000, 16 KiB)
```

The **historical** standalone `pcie_noc_tb.sv` reuses the **existing Compute0 local data NoC**, connecting its CPU initiator NI to the PCIe bridge for isolated testing. It instantiates the same existing SRAM target RTL as the chip. That **isolated stage** has no dedicated PCIe0 NoC, no CPU involvement,
and no configuration-NoC connection. The later full-chip test in PR #60
**does** instantiate the dedicated PCIe0 local data/config networks and
CPU/DMA coordination. PCIe management CSRs are still reserved.

[Real RTL CI at commit d4f307c68019](https://github.com/r987r/xezim-hello-world/actions/runs/41968540566) passed both jobs. The NoC test checks three PCIe BAR read/write patterns against real SRAM readback, and monitors 12 SRAM write and 12 read events through real RTL. The simulator logs `PCIE0_REAL_NOC_SRAM_PASS vectors=3 SRAM_WRITES=12 SRAM_READS=12` at 890 ns simulated time.

## Diagnostic honesty and warning policy

The first standalone green Cocotb test **was not a clean compilation**: Icarus printed four port-width warnings tagged as `ERROR cocotb`; this is now corrected and gated. The PCIe Root Complex normally probes nonexistent functions during enumeration. `discovery.py` filters only these expected negative probes on the **actual upstream RootComplex logger**, and reports `PCIE0_EXPECTED_DISCOVERY_MISSES=30`. The stage-2 confirmed transcript has **zero Cocotb WARNING/ERROR/CRITICAL lines**. Unrelated warnings and actual errors are never filtered.

Verilator 5.020 still reports inherited lint diagnostics when compiling the real PULP/PCIe RTL (at the preceding hardware-equivalent test head: 12 PINMISSING, 306 TIMESCALEMOD, 114 WIDTHEXPAND, 41 WIDTHTRUNC, 5 ASCRANGE, 2 UNSIGNED, 10 SPLITVAR, 2 CASEINCOMPLETE and 13 UNOPTFLAT; no `%Error`). This job compiles with `-Wno-fatal` and is **not lint-clean**; review project/upstream warning provenance and waiver or root-cause fixes in [#32](https://github.com/r987r/xezim-hello-world/issues/32). Do not suppress an entire warning category to manufacture green lint. Two upstream `pcie_tlp_demux` optional sequence ports also generate PINMISSING and warrant an explicit reviewed tie-off.

All actual simulator outcomes are checked through XML and failed or missing captures fail the runner; compile failures print offending Verilator diagnostics. The build and simulation transcripts are saved by the PCIe CI job.

## Reproduction

Pin and clone the upstream repository into ignored `.tools/verilog_pcie`, install the dependencies specified in `requirements-sim.txt`, Icarus Verilog and the existing Bender/FlooNoC/Verilator pinned toolchain:

```sh
python3 -m unittest tests.test_pcie_bar_contract tests.test_pcie_diagnostic_contract -v
python3 dv/pcie0/run_rtl_smoke.py --check-pin
SIM=icarus python3 dv/pcie0/run_rtl_smoke.py
python3 dv/pcie0/run_noc_smoke.py
```

The [dedicated workflow](../../.github/workflows/pcie0-bridge.yml) runs Icarus/Cocotb for stage 1 and Verilator/Cocotb for stage 2. A new GitHub Pages deployment is not needed for isolated PCIe PR smoke tests.

## Remaining optional PCIe qualification (outside initial smoke)

- The dedicated **PCIe0** local data/config FlooNoCs and global SoC links
  are now generated and the data bridge is attached. Real PCIe management
  CSRs remain an unimplemented future endpoint.
- Add multiple outstanding tags, completion fragmentation and negative cases: Unsupported Request, out-of-window, timeouts, burst stalls/backpressure and reset recovery.
- Maintain the now-working unified PCIe TLP/AXI/DDR-model trace and
  host-vs-controller latency report. Expand it to future traffic and PCIe
  outbound/DMA modes without a second monitor or report engine.
- Test PCIe Endpoint-initiated outbound TLP/DMA into actual Root Complex host memory; writing PCIe0 SRAM alone is **not host delivery**.
- Qualify physical PCIe controller/PIPE/LTSSM/SerDes separately; all link/configuration behavior in these tests is modeled.

PR #51 is the historical standalone stage; PR #60 carries the current
combined full-chip path. The initial functional path is proven, while
multi-tag/backpressure, controller CSR, true outbound host-memory DMA and
physical PHY qualification are separate follow-ups.
