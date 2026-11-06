# Ethernet0 end-to-end integration handoff

## What has real RTL today

- MAC + GMII RX/TX, FCS, 64-bit AXI-Stream/CDC and frame staging:
  merged #52.
- Programmable one-RX/one-TX queue model (scalable counts), strict
  EtherType/UDP policy, descriptor fetch and upstream DMA reads/writes
  against actual upstream AXI SRAM: merged #61.
- A separate upstream AXI completion-record writer tested with real
  AXI write responses and frontdoor SRAM readback: merged #68.
- A generic peripheral emitter and the generated Ethernet0 local
  Data/Config FlooNoCs with four global structural links: merged
  #53 and topology consolidation PR #70.

## What is reserved, **not** functional packet routing

The canonical generated full-chip manifest marks Ethernet0
`rtl_attachment: reserved_idle` and
`csr_attachment: explicit_axi_error`.
The diagrams must show the packet ingress and queue register attachment as
**planned**, not wired. No CPU-driven GMII→local SRAM route may be reported as
measured until actual packet traffic has completed through the generated NoC.

## Active end-to-end integration: draft PR #73 / issue #64

The single [integration PR #73](https://github.com/r987r/xezim-hello-world/pull/73) starts from main and currently contains **interface plumbing only**: queue-owned RX/TX CQ slot addresses, RX policy metadata, and TX descriptor/completion hookups, with focused standalone test additions. See the [five named RUN/CHECK acceptance gates](ethernet0-closure-gate.md) and the [source-backed current-status table](implementation-status.md). Standalone queue/MAC/NoC tests being green **do not** prove a connected packet path.

All five steps remain unverified on generated full-chip RTL. Do not merge #73 or close #64 until exact-head CI passes those real-path checks, source-fresh generated RTL and diagrams agree, and the CPU/host sees correct memory and CQ data.

## Remaining end-to-end integration work: issue #64

The single future PR should wire actual RX packet staging, header metadata,
queue policy, descriptor fetch, upstream AXI DMA and SRAM. Reuse the
verified completion-writer module, and only advance the queue's completion
producer pointer after the corresponding packet **and** CQ AXI B responses
are successful. TX must read the selected memory source and confirm GMII
transmission, not just DMA read completion.

Wire the existing queue CSR/doorbell MMIO through Ethernet0's generated
Config FlooNoC. Reuse CPU0 cold boot and common INIT/RUN/CHECK; C and Python
must read the same versioned descriptor ABI. Preserve the existing
source-derived `config/soc.yaml` → `gen/noc/`, `gen/chip/`,
`gen/diagrams/` chain.

### Required exact-head proof before promoting to wired

1. Real Icarus/Verilator elaboration using pinned upstream MAC, FIFO,
   AXI DMA and SRAM modules; all mandatory AXI/AXIS/CSR ports bound, clock
   crossing reviewed.
2. Unsolicited external GMII RX → queue-owned posted descriptor →
   AXI SRAM write → independent SRAM readback → completion record AXI
   write/readback → CPU queue consumer acknowledgment; no CPU intervention
   per packet.
3. Symmetric SRAM→TX AXI DMA→MAC→GMII verification, exact bytes and FCS.
4. Negative tests: bad FCS, multiple rules, no buffer, CQ full,
   descriptor crossing region, AXI SLVERR, reset mid-packet, stream backpressure.
5. Passive AXI/packet correlations in common per-test reports; source SHA
   and all generated manifests/diagrams regenerated from the same head.
   Unobserved and not-yet-wired routes remain `UNMEASURED`.

This is an architecture handoff, not a claim that the end-to-end path
is currently wired. Continue under [issue #64](https://github.com/r987r/xezim-hello-world/issues/64).
