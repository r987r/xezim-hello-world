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
