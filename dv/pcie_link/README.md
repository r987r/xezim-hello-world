# Replaceable PCIe digital-link bring-up

**Scope:** [P0 #76](https://github.com/r987r/xezim-hello-world/issues/76). An
opt-in **Gen1 x1 digital** test experiment; not a silicon transceiver.

## Verified isolated qualification — 2026-11-15

[Exact-head CI for PR #232](https://github.com/r987r/xezim-hello-world/pull/232)
passed 21/21 workflows at `8b935a77d4ba4c61de944cc0de25c30b3a3e6cca`.
The original source-pinned OpenPCIe self-test executed Cocotb 1/1 PASS,
with original PHY FST and decoded PIPE TLP/DLLP capture. The real
independent pcievhost RC also completed BAR configuration, MWr to actual
SRAM through selected OpenPCIe → TLP/AXI → generated PCIe0 FlooNoC, and
MRd/CplD host byte readback, checked by
[connected-memory CI](https://github.com/r987r/xezim-hello-world/actions/runs/43741566984).
This is **isolated digital RTL integration only**; CPU0 Config-NoC DBI
programming, global SoC NoC route, combined cold-boot, wider stress and
silicon PHY are **not qualified**. The source-selected vendor handshake fix
is a recorded local overlay, not pristine upstream; the standalone
FuseSoC qualification uses explicit test-only timing/host FC scheduling.
Keep [#76](https://github.com/r987r/xezim-hello-world/issues/76) open.

## Earlier development history

**Current status / visual architecture:** The cross-connected original
pcievhost RC ↔ OpenPCIe endpoint **reached L0 independently** in
[GitHub Actions run 43099695972](https://github.com/r987r/xezim-hello-world/actions/runs/43099695972).
This proves the isolated **digital-link** test, not full-chip NoC/SRAM transfer.
Separately, later branch-only original Type-0 BAR0 probe/assignment/MSE
sequences and accepted endpoint config TLP completions also passed; neither
is CPU0-controlled endpoint DBI or an over-link memory-to-NoC transaction. See [PCIe fast-versus-real-link architecture,
evidence matrix and report integration](../../docs/pcie-verification-modes.md).
The original modeled-link full-chip reporter remains the default.

The original `chip-pcie-host` Cocotb test remains a **TLP bridge-only**
regression and continues using the existing one common regression/action
framework. It does **not** qualify a real PCIe physical/Data Link/LTSSM path.

## Authoritative sources and replacement seams

1. `config/ip.lock.yaml` selects exact root commits for the OpenPCIe
   endpoint, the pcievhost host model, and its VProc dependency. The root
   gitlink pins any declared endpoint submodules. `tools/ip_fetch.py`
   hydrates only declared submodules without tracking newer revisions.
2. `config/pcie_link.yaml` selects the endpoint **and** host provider and
   binds their original port names. A future replacement edits this profile
   and its immutable IP lock; it must not alter the common YAML test/action
   schema, TLP/AXI scoreboard, or NoC connector.
3. `dv/pcie_link/pipe_x1_adapter.sv` is the explicit replaceable
   16-bit-active-data / two-K-bit Gen1 x1 PIPE-boundary shim. Both sides use the
   **same** 125 MHz parallel clock. OpenPCIe's outer vectors remain 32-bit,
   but upper lanes are inactive at Gen1. pcievhost also needs its 250 MHz symbol
   clock. The adapter preserves valid and electrical-idle behavior, but
   **does not** generate receiver-detect success, `phy_phystatus`, LTSSM
   advancement, or LinkUp. PHY sideband behavior needs an independent
   behavioral source that responds to real endpoint requests.
4. `tools/pcie_link.py` validates exact pin/provider configuration,
   rejects unsupported clock/width/provider swaps, retains explicit
   qualification flags, and emits `gen/pcie_link/selection.json` and
   `gen/pcie_link/README.md` as part of the existing atomic `make gen`.
   These files are source-declaration snapshots, **not executed RTL**.

**Licensing:** pcievhost and VProc are GPL-3.0 and used as isolated
**simulation-only** dependencies; do not add them to synthesizable RTL or
distribute bundled proprietary simulation products without review.
OpenPCIe's README claims MIT but its selected repository root does **not**
contain a LICENSE file. Treat upstream copyright, submodule licenses and
redistribution as *needs review* before copying any vendor source into our
repository or redistributing it.

**PCIe configuration RDL:** the endpoint project's
`src/pcie_cfg/pcie_config.rdl` is its upstream source for PCIe configuration
space, including BAR0 at config offset `0x10`. It is **not**
SoC `pcie0.ctrl` outbound requester MMIO. Do not create a hand-maintained
second PCIe BAR definition or assume the RDL's current access-policy fields
have been proven by actual host config writes. The root complex normally
assigns BAR address only after L0/enumeration.

## Initial reproducible checks

```sh
python3 -m unittest tests.test_pcie_link tests.test_ip_fetch_submodules -v
python3 tools/pcie_link.py --check
iverilog -g2012 -s tb_pcie_pipe_x1_adapter -o /tmp/pipe.vvp \
  dv/pcie_link/pipe_x1_adapter.sv dv/pcie_link/tb_pipe_x1_adapter.sv
vvp /tmp/pipe.vvp
python3 tools/ip_fetch.py pcie_endpoint_openpcie pcie_host_pcievhost pcie_host_vproc
python3 tools/pcie_link.py --check --check-upstream
```

Dedicated `pcie-digital-link.yml` additionally attempts the exact
upstream OpenPCIe FuseSoC/Verilator test and the original pcievhost
Verilator/VProc x1 self-test in separate jobs. Those *standalone provider
self-tests* do not themselves prove the independent cross-connected link,
which is now tested in the separate real `l0`/BAR0 workflow lanes. Logs,
source selection and original upstream exit status are kept in Actions.

## Remaining digital-link and full-chip qualification (partial L0 complete)

- [x] Isolated original host/endpoint compiled digital PIPE/LTSSM reaches
  L0 without forcing LinkUp (independent CI scope, **not full-chip**).
- [ ] Same trained link connected to full-chip NoC/SRAM and CPU0 firmware,
  with genuine host readback and expected physical link transitions.
- Negative tests for absent remote partner, bad ordered sets, link-down,
  receiver detect failure and timeout. No test may succeed because a timer
  merely sets `link_up`.
- Actual Root Complex configuration reads/writes through the trained link:
  BAR sizing/write/read, Memory Space/BME enables, inbound relocation,
  NoC SRAM byte completion, and RDL access semantics.
- Reuse the **same** SCN action/INIT/RUN/CHECK runtime and passive
  TLP/AXI reporters for the existing CPU0 and DMA paths; archive original
  software, generated code, simulator commands and time-ordered evidence
  under canonical per-run IDs.
- An upstream provider can be promoted from `source_declared_not_executed`
  only with exact-commit executed original RTL/PHY/host evidence. Analog
  SerDes/electrical compliance remain out of scope for this digital test.

Do **not** close #76 or treat an upstream self-test, pipe adapter, configuration
header, synthetic modeled link-up, or `pcie_axi_master` alone as a trained
endpoint link.

## Historical L0 bring-up investigation (initial steps now passed; full-chip still missing)

1. Fix the **original upstream Cocotb execution** first. A green build previously
   hid an import failure; the new mandatory result parser rejects zero/failed
   tests even when FuseSoC exits 0. A later run exposed a missing `crc` package.
2. Reuse OpenPCIe's pinned `verif/sequences/pipe_link_up_seq.py` and
   `verif/agents/pipe_agent/pipe_driver_bfm.py` for Detect, TS1/TS2,
   Configuration. The responder in `phy_status_responder.sv` models just
   the PHY-side receiver-detect response (`phy_phystatus` and `3'b011`),
   conditioned on request and remote termination; it never drives link_up.
3. Replace the endpoint half of pcievhost's original
   `verilog/testpipex1/test.v` back-to-back demonstration with real OpenPCIe
   `pcie_phy_top` RTL. Keep root-complex `EndPoint=0`, select `DataWidth=32`,
   and make the RC test software use `InitLink(1)` instead of the original
   demonstration's hardcoded `InitLink(16)`.
4. At Gen1 32-bit, provide the host's 250 MHz `pcieclk`, common 62.5 MHz
   host `pclk` and endpoint PIPE clocks; correctly supply its separate core
   clock. Wire TxData/K in each direction and distinguish electrical idle
   from sample valid. Connect real detect/power/PHY sideband signals.
5. Instrument both LTSSM traces, PHY detect/status, received TS1/TS2
   ordered sets and `link_up_o`; require Detect -> Polling -> Configuration
   -> L0, bounded timeout, no forced `link_up_o`. Negative runs must reject
   disconnected partner, corrupted ordered sets and failed detection, and
   validate reset/retrain.
6. Only after actual L0, qualify host configuration writes, BAR sizing and
   assignment, COMMAND MSE/BME and a real BAR-to-NoC SRAM byte transaction.
   Keep the same canonical regression/action/report lifecycle.

Source example: pcievhost's pinned `src/ltssm.c` explicitly describes its
abbreviated LTSSM as intended for L0 simulation only, not full compliance.
The upstream OpenPCIe self-test and host standalone demo are **different**
from the independently cross-connected RTL/host link test. The original
unaligned 1024-byte / offset-7 Cocotb readback now **passes** with the
exact source-pinned skid-buffer demux correction; a direct randomized
AXI-Stream negative/positive RTL regression protects that fix. Neither
standalone success is full-chip qualification.

## Isolated real host/endpoint/NoC/SRAM byte roundtrip

The `pcie-connected-memory.yml` workflow compiles the **original**
independent pcievhost and OpenPCIe Gen1 RTL, selected endpoint overlay,
the existing pinned verilog-pcie TLP/AXI bridge, generated PCIe0 local
FlooNoC and real AXI SRAM. Its original host performs BAR0 sizing,
assignment, COMMAND MSE, one posted 32-bit MWr to `0x80001100`,
then one MRd from the same address. Native SRAM data/strobe/address
and original host-returned CplD bytes must match `0xa5c36e91`.
The passive `tools/pcie_connected_roundtrip_evidence.py` rejects
missing/repeated/out-of-order events, wrong tag, bytes, address, data or
unqualified original BAR0. Raw host/endpoint simulation output,
source plan and JSON remain CI artifacts. Local RTL execution passed;
the **exact-head independent GitHub CI** is authoritative before merge.

The two explicit verification-only format shims support **only**
one-DW 3DW MWr/MRd and one-DW CplD; unsupported traffic fails
closed rather than silently broadening PCIe claims. No full-chip CPU0
firmware, production NoC readiness handshake, global routing or DMA
integration is demonstrated by this fixture.

## Full-chip parallel boot and PCIe link ownership (integration contract)

**Architecture requirement, NOT an implemented full-chip L0 test.** One selected
SCN action graph schedules `host0.pcie.link.train` concurrently with real
`cpu0` reset/boot/NoC initialization, using the existing CPU/host coordination
and `test-flow` evidence (no separate hardcoded VProc boot sequence).
The host has an **independent** PCIe Root Complex LTSSM and the endpoint
has an **independent** endpoint LTSSM. Their clocks, reset and PHY
Detect/TS1/TS2/configuration ordered sets drive actual training.

Two distinct barriers must never be conflated:

1. **PHY/LTSSM link trained:** RC and endpoint both have *observed* L0;
   a standalone host API returning or a timer is not enough. This may
   happen while CPU0 firmware is still booting and NoC is not ready.
2. **PCIe BAR transaction-ready:** the endpoint configuration/TLP ingress,
   NoC bridges, downstream SRAM and reset/clock paths are initialized,
   address decode has been established, and any CDC FIFOs are operational.
   Host enumeration/configuration after L0 can proceed independently of
   the data-path gate; host MMIO/DMA traffic must wait for an observed
   ready handshake (or receive specified safe completion/retry behavior).
   A CPU mailbox write alone is not hardware acceptance.

**Race-resistant full-chip test requirements:**

- Reset releases independently where appropriate; host begins
  `pcie.link.train`, endpoint LTSSM advances, and CPU0 executes
  immutable-ROM boot/initializes the NoC in parallel.
- CPU0 configures endpoint-accessible resources via the real Config NoC
  and publishes device readiness **only after** NoC routing, memory,
  bridge, and relevant firmware-owned queues are actually initialized.
  A ready flag cannot be merely synthesized by TB time.
- Host observes L0, performs actual config reads, BAR sizing/allocation
  and legal COMMAND settings, then waits for real device-ready capability
  before issuing BAR memory transactions.
- Verify one host MWr/MRd through endpoint TLP decoding -> PCIe0 local
  NoC -> global/local fabric -> SRAM, with passive TLP and AXI completion
  evidence plus independent byte readback. A posted MWr is verified by
  memory visibility, not an invented completion TLP.
- Negative scenarios: L0 before NoC-ready (no early accepted memory
  corruption), NoC-ready before L0 (no fabricated link), absent RC,
  endpoint reset during traffic, CPU boot timeout, and link retraining.
  Host must not deadlock CPU boot by waiting for a transaction requiring
  the not-yet-ready fabric.
- The scenario graph records `actor`, selected seed, plan SHA,
  `depends_on`, and action IDs for both host/CPU. Driver events are
  **not** protocol PASS; passive monitors and the existing independent
  checker must demonstrate the barriers and byte-level completion.

The current `tb_pcie_cross_link.sv` does **not** instantiate the full SoC,
run CPU firmware, or prove a CPU-driven NoC transaction-ready handshake.
It now has a source-selected, opt-in **isolated genuine endpoint→bridge→
generated PCIe0 FlooNoC→SRAM** memory fixture, with independent host
CplD readback. The local fixture asserts its own readiness at reset
release and **must not** be cited as CPU0/Config-NoC initialization.
Full-chip concurrent boot remains a separate gate using the canonical
`tools/regress.py`, scenario actions and reporting contract.

## Device-programmed BAR before LTSSM (pre-link hardware milestone)

The **endpoint owns BAR capabilities** (type, aperture, local target) before
the RC enumerates it. The RC later assigns the *PCI bus address*; never
pre-program the bus address into the device as a substitute for enumeration.
The device-local `endpoint_prelink_ctrl.sv` now accepts proposed BAR0 aperture
and local SRAM target via a test-owned, single-cycle configuration register
port; after validating size/power-of-two/target bounds and alignment, a
`COMMIT` write freezes the chosen geometry, then a separate `START`
write can release actual OpenPCIe `en_i` and `phy_ready_en`.
No premature LTSSM launch is permitted. Requesting START before COMMIT,
late BAR changes, invalid size, misalignment or partial CSR writes fail
closed. See `tb_endpoint_prelink_ctrl.sv` and dedicated source contract
CI. BAR memory acceptance is *independently* gated by `link_up_i`,
`noc_ready_i` and `host_mem_enable_i`; link training does not require
the NoC to be ready.

In isolated `tb_pcie_cross_link.sv` the pre-link writes are provided by an
**explicit TB surrogate**, not by CPU0 firmware or the Config NoC. This
proves only sequencing/gating; it does not qualify the full-chip boot path.
The provided 4KiB/1MiB apertures are test cases, not claims that the pinned
OpenPCIe upstream config space or PCIe host sees these values.

**Historical upstream BAR limitation (resolved for isolated host enumeration via reviewed overlay; full-chip CPU ownership still missing):**
the pinned OpenPCIe `src/pcie_cfg/pcie_config.rdl` defines BAR0 at 0x10
as hardware-readable, software-read-only fields with a constant reset/mask;
the generated `pcie_config_reg.sv` hardwires those values, and the existing
cross-link bench instantiates `pcie_phy_top` only, *not* the upstream
`pcie_cfg_wrapper`/TLP configuration path. The new local pre-link
controller is **not yet wired to those actual host-visible registers**.
Proper integration must expose a configurable BAR advertisement using
an upstream-compatible SystemRDL/PeakRDL generation path, connect the
actual upstream configuration TLP decoder/completion and use selected
Config-NoC/CPU0 firmware to program/commit the endpoint BAR capabilities.
Then host BAR sizing/read/write and local SRAM NoC translation are separate
required real-TLP/AXI acceptance. Do not claim those from the unit gate.

The original `pcie0.ctrl` SoC aperture currently belongs to the outbound
requester CSR; pre-link controller CSRs need explicit nonoverlapping source
ownership within it or another generated address region. Do not alias
endpoint Type-0 configuration space with the CPU's Config-NoC CSR aperture.

## Pinned configuration-TLP BAR overlay experiment — NOT qualification

To keep the upstream generator and config TLP path instead of building a
second PCIe config model, this branch now contains:

- `pcie_bar0_host_cfg.sv`: observes accepted AXI-Lite configuration writes
  and reads from the pinned upstream `pcie_cfg_wrapper`, implements BAR0
  all-ones size probing, RC-assigned PCI bus base and COMMAND.MSE overlay.
- `tools/pcie_cfg_overlay.py`: checks the original upstream
  `src/pcie_cfg/pcie_cfg_wrapper.sv` git blob and replaces only explicit
  source-qualified handler/read taps in the ignored pinned provider checkout.
  It keeps the original `pcie_config_decode`,
  `pcie_config_handler`, `pcie_config_mux` and generated
  `pcie_config_reg` intact. The overlay is experimental and must be
  regenerated/owned through the SystemRDL/PeakRDL source path before
  production integration; no vendor source is silently modified.
- `tb_pcie_cross_link.sv` now connects real endpoint RX TLP to the
  upstream config wrapper and routes generated config completions back to
  endpoint TLP TX. When `VERIFY_REAL_MEM_WRITE=1`, actual received nonconfiguration
  TLPs feed a one-3DW/one-DW-only verification shim into the real
  PCIe bridge and FlooNoC. Other link modes retain their original
  isolated configuration/ingress boundaries.
- `bar0_noc_translate.sv` computes PCI bus-address offset -> local SRAM
  destination under the separate L0, NoC-ready and host-MSE gate. It does
  not accept AXI beats or synthesize completions.
- Focused RTL unit tests cover BAR probe, assignment, command bits,
  misconfiguration, out-of-window requests and independent AXI-Lite AW/W.

**Critical acceptance still open:** source overlay elaboration must PASS,
both real LTSSMs must reach L0, host must issue real configuration TLP
BAR probe/assignment/MSE and independently capture received completions,
then actual nonconfiguration BAR TLP needs a real PCIe-to-FlooNoC bridge
and byte-checked target readback. Also verify the upstream RDL readonly
BAR0's AXI response semantics: an overlay seeing a write is not sufficient
if the original register block rejects it. No test in this branch claims
the config path passes until the exact-head simulator proves it.

## Explicit simulation-only LTSSM acceleration

Source-backed behavior follows AMD's documented fast PCIe simulation pattern:
millisecond LTSSM watchdogs are shortened by 512x and the required number
of **transmitted** Polling.Active TS1s is shortened from 1024 to 16. In
the pinned OpenPCIe provider, the reviewed overlay changes the existing
`SIM_FAST_LINK` timing parameters; the top-level cross-provider bench exposes
the plainly named `SIM_FORCE_FAST_LTSSM` elaboration parameter.

- Default **OFF** for the endpoint and all production uses. The isolated
  cross-link CI explicitly passes `-GSIM_FORCE_FAST_LTSSM=1`.
- Logs must include both
  `PCIE_SIM_FORCE_FAST_LTSSM: ENABLED override=512x` and
  `PCIE_EP_SIM_FAST_LTSSM: ENABLED timer_divider=512 min_tx_ts1=16`,
  including effective timer cycle counts; CI validates these before calling
  the selected run qualified.
- Original Detect/TS receive/Configuration/L0 state machine, receiver-detect
  requests, TS decoding, and real link wires are unchanged. Reducing
  transmit counts **does not** fabricate received TS1/TS2. Link success
  still requires independent RC and endpoint L0 plus observed physical
  training from the original components.
- This is explicitly an acceleration of PCIe wait windows for tests. Do not
  treat it as a fix for incorrectly encoded, timed or lane-aligned PIPE
  ordered sets, and keep slow-timing qualification for later.

Source reference: AMD Versal register manual `PL_SIM_FAST_LINK_TRAINING`
(512x millisecond intervals, 16 TS1s in simulation, must remain disabled
for non-simulation use).

## Actual Gen1 PIPE width interoperability

The pinned OpenPCIe `src/pcie_phy_core/lane_management.sv` declares
`PipeWidthGen1 = 16`, regardless of its outer 32-bit-wide RTL vector.
The original cross-provider simulation incorrectly clocked the 32-bit
pcievhost at 62.5 MHz while the endpoint sent/consumed **two bytes per
beat**. Its passive waveform confirmed host words delivered to a 16-bit
ordered-set parser, causing 0 decoded TS1/TS2.

The cross-provider harness now uses original pcievhost `DataWidth=16`,
the matching 125 MHz Gen1 PIPE clock, exactly two data bytes and two
K flags per physical beat, and a passive run-time check of
`pipe_width_o == 16`. The surrounding 32-bit OpenPCIe RTL port is
zero-extended; its inactive upper bytes must not be interpreted as
valid PCIe symbols. The canonical SCN action's `data_width_bits`
describes the **active PHY parallel width**, not the nominal vector
size of `phy_txdata`.

Host and endpoint still run independently, with no software-side
crosslink. The remaining exact-head CI must demonstrate received
ordered sets and both genuine LTSSMs in L0; width matching alone is not
a PCIe PASS.

## Mainline qualification checkpoints

- PR #228: BAR0 complete-span address protection and Icarus RTL tests have
  merged into main; full-chip nonconfig TLP path still requires completion.
- PR #229: independent endpoint prelink, host Type-0 BAR and behavioral
  PHY receiver-detect RTL benches have merged; CPU0 Config-NoC remains
  unconnected to the endpoint prelink hardware in the full SoC.

## Active PR #232: surviving completion-failure gate

[Issue #76](https://github.com/r987r/xezim-hello-world/issues/76)
records current authoritative acceptance. The original OpenPCIe
`test_pcie_core.link_up_test` on draft head `2bdbb2c` failed
in [run 43413751149](https://github.com/r987r/xezim-hello-world/actions/runs/43413751149),
where host MRd tags 10, 11 and 12 requested 1024 bytes at offset 7.
Endpoint logs show segmented CplD construction but no complete host
readback. The temporary retry-reservation overlay worsened this to
offset 1 and was reverted; its ACK/FIFO behavior was not independently
validated. This was an earlier **historical RED** checkpoint; the patched, source-pinned
RTL subsequently passed the exact-head original byte-readback CI linked above. Distinguish endpoint CplD driver
completion from accepted DLL/PIPE output and independent RC receipt.

The subsequent isolated real-link→NoC→SRAM→CplD run meets the *connected*
host-to-memory checkpoint, not full-chip acceptance. CPU0 Config-NoC
prelink programming, full-chip cold boot and global integration remain
required. Analog SerDes remains out of scope.
