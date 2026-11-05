# PCIe0 RC + CPU0: common INIT/RUN/CHECK and TestML-shaped integration

## Current RTL truth

This stacked branch targets the already-generated PCIe0 subsystem from PR #53.
The verification design uses **real pinned alexforencich verilog-pcie**
`pcie_axi_master` TLP-to-AXI4 conversion, the **real generated PCIe0 local
data FlooNoC**, existing global data/config FlooNoCs, a bounded real
`axi_sram_target` backed by upstream PULP SRAM, and the standard CPU0+SERV
boot/phase checker.

**The Root Complex, Endpoint simulation link and enumeration are modeled**
using `cocotbext-pcie`. There is no physical PCIe PHY, PIPE, LTSSM or board
clock recovery here. Do not mislabel the test as PHY/link-training signoff.
The PCIe0 local config NoC is real, but its controller CSR endpoint still
returns an explicit AXI error because endpoint CSR RTL is not yet attached.
PCIe0 outbound DMA, MSI/MSI-X, tag stress, link recovery and host-memory
read/write remain follow-up verification tasks.

## Reuse the existing execution methodology

Executable entry point: `python3 tools/regress.py chip-pcie-host`.
The `chip-pcie-host` entry in `config/regression.yaml` selects **the
existing Cocotb/Verilator runner**, the same generated chip RTL and shared
CPU0/CPU1 firmware coordinator, the existing passive AXI monitor catalog,
and the single published run-report schema. `firmware_mode: pcie_host`
generates the opt-in boot image and chip wrapper only inside
`.tools/regression/chip-pcie-host/variant`. No cold writable SRAM is
preloaded and tracked `gen/` remains unchanged.

The test is split into actors with explicit resource ownership:

| Actor | INIT | RUN | CHECK |
| --- | --- | --- | --- |
| CPU0 RTL firmware | ROM-copy CPU images, release secondary, wait for CPU acks; publish device-ready to PCIe0 SRAM | Receive host init ack; publish host-run-enable; wait for host traffic completion | Wait for peer CPU ack; publish check-enable; wait for host check ack; write normal final CPU done marker |
| CPU1 RTL firmware | Acknowledge normal boot/init | Execute existing hello/peer coordination | Acknowledge real CPU check |
| Host RC model | Own RC topology, enumerate endpoint, enable function and BAR; poll device-ready then write host init ack through BAR | Wait for run-enable; issue TLP writes and reads; independently check returned bytes; write host-run ack | Wait for check-enable; verify no endpoint error and accepted SRAM traffic; write host check ack |
| Common phase checker and passive AXI monitors | Observe actual CPU INIT and link transactions | Capture AXI4 AW/W/B/AR/R by source, destination, address, ID and response | Require CPU masks, CPU done, host acknowledgements and end-to-end payload matches |

The shared handshake occupies **PCIe0 SRAM bytes 0x800 through 0x817**,
relative to `pcie0.sram` at `0x12000000` (variant-specific address is
resolved from `config/soc.yaml`). CPU0 reaches it via
compute0.local_data -> global_data -> pcie0.local_data -> SRAM. The host
reaches those same bytes via BAR0 -> real pcie_axi_master ->
pcie0.local_data -> SRAM. These are **frontdoor transactions**, not Cocotb
forcing signals, preloading RAM or writing Python-only completion flags.

The handshake consists of three CPU0-initiated pairs:

1. INIT: `device_init_ready` at offset 0x800; host acknowledges at 0x804.
2. RUN: `run_enable` at 0x808; host acknowledges completion at 0x80c.
3. CHECK: `check_enable` at 0x810; host acknowledges checking at 0x814.

The existing CPU-only test retains its 256-byte flash image slot and default
checker. Only this opt-in joint-actor variant explicitly authorizes a
512-byte flash slot, still below the original mailbox/descriptor partition.

## Proposed next TestML-level abstraction (not yet a generic interpreter)

Avoid a PCIe-only `run_test.py` architecture. Introduce declarative
`config/testml/<scenario>.yaml` scenarios that the existing regression
runner can pass to a shared phase engine. The engine should own phase
barriers, actor activation, memory allocation/reservation, negative-case
expectations, scoreboard and artifact metadata; adapters only implement
transport-specific actions:

```yaml
schema_version: 1
scenario: pcie0_host_bar_roundtrip
transport: pcie
actors:
  cpu0: {kind: rtl_firmware, role: device_initializer}
  host0: {kind: cocotb_pcie_rc, role: host_enumerator}
  endpoint0: {kind: rtl_pcie_tlp_to_axi, subsystem: pcie0}
phases:
  init:
    require: [cpu0_rom_boot, cpu1_init_ack, host0_enumeration, bar0_enabled]
    barrier: device_init_ready_and_host_init_ack
  run:
    require: [host0_bar_write, host0_bar_read, pcie0_sram_axi_accept]
    barrier: run_enable_and_host_run_ack
  check:
    require: [payload_scoreboard, cpu0_check, cpu1_check, host0_check]
    barrier: check_enable_and_host_check_ack
resources:
  - {region: pcie0.sram, offset: 0x100, bytes: 128, owner: host0, phase: run}
  - {region: pcie0.sram, offset: 0x800, bytes: 24, owner: shared_phase_mailbox, phase: all}
reports: [axi_events, protocol_events, cpu_phase_timestamps, memory_operations]
```

This YAML is an **API proposal**, not a claim that a generic TestML parser
currently executes it. The executable `config/regression.yaml` remains
authoritative in this PR. Prefer extracting the three handshake word pairs
and host vector manifest into the shared schema in the follow-up, so CPU C
or ROM firmware, host BFM and checker use the same generated ABI.

### Reuse with Ethernet0 and future interfaces

The same actor/phase contract works when `host0` becomes a GMII/UDP peer,
and `endpoint0` becomes Ethernet0 MAC + queue manager + AXI/stream DMA.
Peripheral transport must not implicitly claim memory ownership; RX needs
preposted destination descriptors before the host sends the first frame.
The CPU0 INIT phase owns queue/buffer setup and programming; RUN can have
asynchronous ingress at arbitrary times. Host and CPU0 CHECK must wait for
queue drain, DMA completion and all packet/data scoreboards, not just an
acknowledged host send.

## Acceptance before marking the PCIe subsystem complete

- Exact SHA from this stacked PR, green unit tests, generated code drift and real Verilator RTL simulation.
- Both CPU0 and host ack through real NoCs/SRAM; missing/late host ack must time out.
- At least four host BAR read/write vectors including unaligned partial writes,
  with independent data reference and passive accepted SRAM counters.
- Run-report metadata identifies the actual pcie0 host NoC initiator and shows
  CPU0's remote phase stores at pcie0 SRAM, not an invented measurement.
- The host and CPU checker report one success only after all three phases;
  actual physical link training, outbound host DMA and controller CSR must
  remain explicitly unverified until separate PRs demonstrate them.

References: PR #51 (standalone bridge); PR #53 (generated PCIe0 fabrics);
this stacked PR #60 (CPU/host integration); issues #36, #38, #41, #44.
