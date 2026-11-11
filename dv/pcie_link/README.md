# Replaceable PCIe digital-link bring-up

**Scope:** [P0 #76](https://github.com/r987r/xezim-hello-world/issues/76). An
opt-in **Gen1 x1 digital** test experiment; not a silicon transceiver.

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
   32-bit-data / four-K-bit Gen1 x1 PIPE-boundary shim. Both sides use the
   **same** 62.5 MHz parallel clock. pcievhost also needs its 250 MHz symbol
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
Verilator/VProc x1 self-test in separate jobs. These **are not** yet the
cross-connected real endpoint/host L0 proof. Logs, source selection and
original upstream exit status are kept in GitHub Actions artifacts.

## Required real-L0 qualification (still open)

- One compiled cross-connected full-chip digital PIPE test with a behavioral
  PHY responder, actual clock/reset wiring, observed ordered-set exchanges,
  LTSSM progressing into L0 **without forcing LinkUp**.
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

## Current L0 bring-up investigation (NOT yet connected)

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
The upstream OpenPCIe self-test and the host standalone demo are **not**
cross-connected. No current result establishes L0 training.

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
run CPU firmware, or implement the NoC transaction-ready handshake.
It remains an isolated link-training experiment. Implement the full-chip
parallel boot only *after* actual isolated L0 evidence is green; reuse
`tools/regress.py`, `config/regression.yaml`, original SCN-C/Python/SV
action ABI and `dv/pcie0/host_adapter.py` instead of copying an independent
test runner.
