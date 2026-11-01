# Hierarchical verification plan

All scopes consume the same `config/soc.yaml` and use shared AXI monitors, reference models, and route manifests. The testbench verifies the **RTL actually under test**, rather than reporting a green result from a VIP-to-VIP loop.

## Implemented scopes

| Scope | RTL under test | Check |
| --- | --- | --- |
| Generator/configuration | SoC schema, address maps, fabric backend registry | Determinism, invalid configurations rejected |
| Memory-local fabric | Verilog-AXI 2×2 crossbar with HBM and DDR behavioral AXI targets | Every ingress writes/reads both targets, ID route, data, ordering of burst beats |
| Negative memory check | Same RTL, corrupted expected read data | Must produce `FAIL AXI read` |
| CPU instance smoke | Public PicoRV32 + SERV RTL | Both elaborate and independently issue fetch requests |

A memory model responding to AXI does **not** test its selected HBM/DDR controller or PHY. The two CPU smoke instances have no software/SoC network attached.

## Expansion sequence

1. **Local compute fabrics:** instantiate local AXI4 and AXI4-Lite crossbars; connect PicoRV32 and SERV to protocol bridges and local SRAM; prove local accesses.
2. **DMA subsystem:** integrate PULP iDMA in each compute instance; execute SRAM-to-remote DDR/HBM copies; independently compare memory contents.
3. **Global NoCs:** generate FlooNoC data topology and a separate config fabric from vendor-neutral IR; test routing, outstanding IDs, fairness, and congestion.
4. **Controller integration:** separately verify LiteDRAM with open DDR DFI model; investigate HiSA HBM with necessary vendor IP or alternative fully open model, without claiming silicon-grade PHY fidelity.
5. **Full chip:** real CPU firmware programs DMAs, simultaneous access to HBM/DDR, memory consistency, interrupts, and independent progress of config traffic under bulk data congestion.
6. **Scalability:** add compute2 and memory1 using configuration only; regenerate topology and auto-expand source-to-destination coverage.

## Acceptance gates

- Every configured and reachable source/target path performs a real completed transaction.
- A scoreboard independently checks memory contents and read/write responses.
- AXI VALID/READY, bursts, ID extension, ordering and unmapped-address errors are checked.
- A negative mutation must be detected for the intended reason.
- Each regression has a finite simulation timeout, deterministic seed, and failure logs.
- Backends and IP adapters have explicit capability/status declarations and reject unsupported use.
- Simulator provisioning is separate: only HDL/configuration changes cause HDL re-elaboration; Rust/Xezim is not rebuilt.
