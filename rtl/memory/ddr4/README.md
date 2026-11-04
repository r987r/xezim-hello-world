# DDR4 controller bring-up — isolated track

**Status: configuration and contract scaffold only.** This directory does not instantiate a DDR controller in the chip, replace the bounded AXI SRAM stand-in, or establish DDR4 initialization/timing/data transfer.

## Scope and parallel-work guardrail

This PR changes **only rtl/memory/ddr4/**. Do not disturb concurrent CPU, DMA, NoC, AXI reporting, boot firmware, or documentation work. Ask for explicit approval before **substantial changes outside rtl/memory/**, in particular:

- config/soc.yaml, config/ip.lock.yaml, config/interface_contracts.yaml, config/regression.yaml, Bender.yml
- tools/full_chip_gen.py, tools/generate.py, tools/regress.py, tools/supernoc_gen.py, shared adapters or NoC generators
- .github/ CI, Makefile, generator-owned gen/ or generated README sections

Before touching such files, present the exact files, proposed diff size, reason, integration risk and test plan. Do not merge this PR or rebase unrelated work without review. All subsequent stages must retain the checked-in CPU cold-boot proof.

## Existing system contract (unchanged)

- Target memory0.ddr0: architectural 1 GiB window [0x140000000, 0x180000000), via the global and memory-local FlooNoCs and crossbar.
- Configured data NoC: 64-bit system address, 64-bit data, 4-bit target IDs. Recheck the generated endpoint manifest before attachment.
- Current chip-boot memory target: **64 KiB bounded** PULP AXI-to-memory + SRAM model, already exercised by the verification BFM. Deliberate just-outside-capacity SLVERR is intentional.
- The two CPUs are 32-bit and cannot directly address this DDR window above 4 GiB; this is a DMA/AXI manager address space unless a later CPU address extension is introduced.
- memory0.ctrl is a reserved configuration-NoC CSR window, **not an implemented DDR register block**.

Do not modify the cold-boot firmware paths, the existing negative response tests or the planned HBM target as part of DDR bring-up.

## First controller: pinned LiteDRAM

| Component | Selection | Meaning |
| --- | --- | --- |
| RTL + AXI frontend | [LiteDRAM](https://github.com/enjoy-digital/litedram) | Generated Verilog from immutable upstream commit; no local RTL fork |
| DDR4 PHY + device behavior | LiteDRAM --sim / SDRAMPHYModel | DFI-level simulation model, not an ASIC production PHY |
| Fast baseline | Existing PULP AXI+tc_sram target | Remains the default for full-chip boot and regression |
| Alternative evaluation | [YuQuan Baiyang](https://github.com/OpenXiangShan/YuQuan) + TinyPHY | Isolated comparison later; do not add shared pin without approval |
| Timing exploration | [Ramulator2](https://github.com/CMU-SAFARI/ramulator2) | Architectural timing model, not RTL PHY verification |

Existing LiteDRAM pin in config/ip.lock.yaml:
3506dc02e2b790011c1c147e2aad4541a6ddf836 (BSD-2-Clause).

The local profile specifies DDR4, one rank, eight x8 DRAM devices, 64-bit user AXI data, 4-bit AXI IDs and enabled refresh. Upstream --sim replaces the FPGA PHY with its DFI simulation PHY/model. The physical DRAM density and address geometry must be checked independently against the 1 GiB architectural window.

**Initialization prerequisite:** the profile uses CPU=null to expose the upstream Wishbone wb_ctrl initialization interface. A future cocotb test must implement the upstream initialization sequence, wait for init_done and fail on init_error. The AXI port is blocked until ready; this is intentional.

**AXI adapter prerequisite:** LiteDRAM's generated frontend does not expose all NoC AXI4 sidebands (notably some cache/prot/qos/region/user/lock/atop). It also uses a controller-local address width, not 64-bit absolute physical addresses. A reviewed boundary must:
1. Check the full 64-bit window before subtracting the base; no silent high-bit truncation, wrapping, or aliasing.
2. Reject or explicitly adapt unsupported sidebands, exclusives, atomics and burst types.
3. Preserve AXI ordering/ID responses, byte strobes, read/write bursts, backpressure and transaction budgets.
4. Connect DDR init/status to the configuration NoC using upstream bridge IP and reviewed clock/reset handling.
5. Remain configurable for more DDR channels, without cloning the controller or NoC fabric.

## Local commands

Static checks (PyYAML from the existing root requirements):

    python3 -m unittest discover -s rtl/memory/ddr4 -p 'test_*.py' -v
    python3 rtl/memory/ddr4/bringup.py check

Optional pinned upstream RTL-generation attempt, in a network-enabled environment with LiteX/Migen dependencies:

    python3 tools/ip_fetch.py litedram
    python3 -m pip install -e .tools/litedram
    python3 rtl/memory/ddr4/bringup.py generate
    python3 rtl/memory/ddr4/check_rtl.py --tool both  # separate compile-only results

Generation uses local sim_model.py --sim, invoking pinned upstream litedram.gen with simulation-only reduced geometry (rather than editing upstream RTL). It writes only beneath ignored .tools/ddr4/ (enforced by a negative path guard), not the generator-owned gen/ tree. Successful generation produces a SHA-256 manifest and **generated-not-simulated** status; it is not a simulation pass.

## PR milestone tracker

- [x] Stage 0: Dedicated branch and memory-only scaffold; existing top-level files untouched.
- [x] Stage 0: Pin reference, DDR4 profile, static interface/address checks and negative unit tests added.
- [x] Stage 0: 38 memory-only Python unit tests pass locally, including negative signal-direction/address-width cases and both simulator command shapes.
- [ ] Stage 0 acceptance: run `bringup.py check` against the complete repo and capture local/CI DDR-only evidence on the final PR SHA; current shared SoC workflows do **not** run this memory-directory test suite.
- [ ] Stage 1: Generate real DDR4 LiteDRAM + simulation-PHY Verilog from pinned source. Record generated port map, CSR map, build commands, hashes and all dependency revisions.
- [ ] Stage 1: Isolated Verilator elaboration **and** independent Xezim compatibility check. Do not misreport structural compilation as traffic.
- [ ] Stage 2: Initialize controller over wb_ctrl, check init_done/init_error, reset/reinit.
- [ ] Stage 2: Reuse cocotbext-axi and independent scoreboards: reads/writes, bursts, byte strobes, narrow/unaligned requests where supported, multiple IDs, ordering, backpressure, refresh and negative cases.
- [ ] Stage 2: Collect bandwidth/latency/outstanding/refresh statistics and document unsupported operations.
- [ ] **Stage 3: APPROVAL REQUIRED** — propose a small, explicit shared-file diff for full-chip backend selection, generated RTL/filelists, memory CSR, CI/regression hooks and NoC integration. Obtain approval *before* edits outside the memory subsystem.
- [ ] Stage 3: After approval, opt-in real DDR simulation backend while preserving fast SRAM default, cold boot, existing negative tests and dual simulator gates.
- [ ] Stage 3: After approval, routed DMA/CPU-originated AXI traffic and passive DDR statistics in the per-test AXI report (no duplicate observations).
- [ ] Stage 4: Compare YuQuan/TinyPHY in an independent scope; justify any switch with measured results, licensing, and tool support.
- [ ] Stage 5: Open a separate HBM bring-up PR only after DDR milestones are accepted.

**Evidence rule:** a static check, generated RTL, elaboration, initialized simulation and passing AXI transactions are separate claims. An AXI RAM/SRAM regression is *not* proof of DDR controller/PHY operation. Mark a stage complete only with logs from the matching PR head commit.

## Simulation capacity and evidence (2026-11-04)

The selected upstream MT40A512M8 configuration (8 x8 devices, 16 banks,
32768 rows, 1024 columns) represents **4 GiB** of x64 device storage.
The upstream DFI PHY model expands this into dense per-bank simulation
memories: generating/elaborating the full-size model can be prohibitively
expensive. The isolated sim_geometry.yml intentionally reduces rows to
2048 and columns to 128, retaining 16 banks and the DDR4 command-address
A10 requirement. This yields **32 MiB** of *non-JEDEC production geometry*. The generator wrapper preserves the original **15-bit DDR4 DFI command address** even though its simulated row storage uses 11 bits, avoiding accidental truncation of DDR4 mode-register command bits. The controller still sees the smaller row/column geometry, so this is an isolated functional model, not an accurate full-capacity DDR4 device.
The budget checker caps it at 64 MiB and rejects unexpected source
geometry. This override applies **only to --sim generation**, with no
upstream LiteDRAM file modifications. Use the real geometry/timings and an
approved physical PHY when targeting hardware. The 1 GiB architectural
SoC address window remains unchanged and **must not alias** the isolated
32 MiB modeled capacity: an approved memory-window adapter must explicitly
reject out-of-model accesses.

Local check performed (Python 3.13 + PyYAML):

    python3 -m unittest discover -s rtl/memory/ddr4 -p 'test_*.py' -v
    # Ran 38 tests, OK

This verifies Python contract/negative cases, signal direction, control-port requirements, safe compile-command planning and capacity calculations,
**not real generated Verilog**. The execution container lacks internet
resolution for github.com, Verilator, Xezim and LiteX/Migen; thus pinned
upstream generation, HDL elaboration and DDR AXI traffic are not yet
executable here. The regular SoC PR workflows passed at previous head
b118adaf3e4724285a9b1596a91f1b8d35284084; new commits must get
their own green results before merging.

## Upstream debugging references and isolated compile gate

The generated core exports LiteX Wishbone `wb_ctrl`, plus DDR init
status. The memory-only port checker now checks full AXI5-channel
request/response **directions**, WSTRB/ID/data widths, controller-local
address width (32 MiB = 25 bits), user clock/reset, init/error status,
and Wishbone control pins (including CTI/BTE/ERR). Fake ANSI Verilog
fixtures exercise these checks; they do **not** establish that the actual
pinned LiteDRAM generator emits precisely these pins. Generation will
fail closed if upstream output differs.

After successful RTL generation:

    python3 rtl/memory/ddr4/check_rtl.py --tool verilator
    XEZIM_BIN=/path/to/xezim python3 rtl/memory/ddr4/check_rtl.py --tool xezim

The independent checks generate a local filelist and save
`verilator.log`, `xezim.log`, and `ddr4_compile_results.json` under
ignored `.tools/ddr4/litedram_sim/`. A missing Verilator/Xezim binary,
missing generated source, nonzero compile or timeout is a failure, not a
pass. The Xezim command matches this repo's existing
`--compile --no-cache -s <top> -f <filelist>` convention.
**Neither engine has actually compiled this DDR4 RTL yet.**

If generation raises a Python traceback under Python 3.13, examine the
**historical, closed** [upstream LiteX issue #2152](https://github.com/enjoy-digital/litex/issues/2152)
(issues around Migen/CSR name extraction were reported in 2024 and issue
closed in February 2025) before creating any local Migen/CSR monkeypatch. Use Python 3.11 as
a conservative isolated-generator baseline and record **actual**
Migen/LiteX versions; pin those dependencies in the memory subsystem
once a working combination is demonstrated. Do not claim Python 3.13
is necessarily broken: that issue may be fixed in newer releases.

For Verilator slowdown/OOM, check its
[memory/runtime FAQ](https://veripool.org/guide/latest/faq.html),
the generated DFI model's dense bank memories and the simulation-only
geometry limit. Do not disable refresh, silently delete model storage
or invent a fake DDR/PHY stub to make tests green.

Expected functional follow-up: use upstream LiteDRAM
[standalone generator documentation](https://github.com/enjoy-digital/litedram/blob/3506dc02e2b790011c1c147e2aad4541a6ddf836/doc/gen.md),
initialize over Wishbone `wb_ctrl` (CPU is null), wait for
`init_done` and ensure `init_error` is low, then run cocotbext-axi
transaction/scoreboard tests against **real generated controller +
DFI simulation PHY**, not the existing AXI SRAM stand-in.

## Controller startup plan (generated, not yet executed)

With `cpu: null`, the standalone core exports `wb_ctrl` but has no
on-chip firmware to perform DDR4 initialization. Rather than invent
mode-register values, `sim_model.py` now uses the pinned upstream
`litedram.init.get_sdram_phy_init_sequence()` with the exact DDR4
PHY model settings and timing derived from the selected device.
It emits `.tools/ddr4/litedram_sim/ddr4_init_plan.json` containing:

- Reset release and CKE commands
- DDR4 mode-register programming for MR3, MR6, MR5, MR4, MR2, MR1, MR0
- ZQ calibration
- Symbolic upstream command and control masks, bank/command address,
  and source BIOS delay units

The plan remains **plan-only-not-executed**. `bringup.py generate`
requires a nonempty, clock-matched generated init plan, but nobody has
yet driven the Wishbone bus, awaited `init_done`, completed DRAM
initialization, or run AXI traffic. In a future cocotb test, derive CSR
addresses from the generated CSR map, translate the upstream BIOS delay
units into verified simulation waits, and use the upstream control
register sequencing; do **not** simply force init_done high.
