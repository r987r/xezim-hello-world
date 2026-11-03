# Hierarchical verification plan

`config/soc.yaml` declares executable and planned scopes, reflected in
`gen/verification/plan.json`. Generated memory/boot/NoC scopes derive their
addresses and topology from that configuration. Standalone CPU/SRAM checks
remain independent bring-up tests. There is one architecture diagram;
verification details live in source, manifests and logs.

`gen/verification/routes.json` enumerates the separate memory crossbar's
expected paths. `gen/supernoc/manifest.json` records the connected NoC
wrapper's source windows, leaf destinations, network paths and AXI links.
`make check-generated` checks exact artifact names and contents. Each
fabric scope drives actual interconnect RTL; the connected NoC scope
uses upstream AXI agents.

## Implemented scopes

| Scope | RTL under test | Checks |
| --- | --- | --- |
| Generator/configuration | SoC schema, addresses, backends and generators | Determinism, invalid configurations rejected, generated-file drift |
| Memory fabric | Verilog-AXI 2×2 crossbar and HBM/DDR behavioral targets | Default/full/sparse routes, responses, IDs, burst data and denied-path DECERR |
| Negative memory check | Same crossbar with a corrupted expectation | Must fail with the intended `FAIL AXI read` diagnostic |
| Local SRAM | Existing reusable dual-port SRAM test model | Uninitialized power-up, byte strobes and both ports |
| SERV execution | Real SERV and standalone Wishbone RAM | Three instructions execute and store the checked signature from a four-word image |
| CPU cold boot | PicoRV32/SERV, ROM, flash, blank SRAM and reset MMIO | CPU0 copies both programs through bus stores, releases CPU1 and both produce signatures |
| Connected NoC BFM | All eight real FlooGen data/config meshes | All 28 mapped source/window routes, intended storage, concurrent reused IDs with distinct stream payloads, bursts, byte guards, stalls, SLVERR and corruption detection |

The legacy CPU fetch smoke is an optional diagnostic, outside the required
CI suite. [Boot details](boot.md) distinguish real instruction execution
from request-only smoke checks. The connected NoC scope uses AXI BFMs at
real endpoint boundaries; it does not attach CPUs, iDMA, AXI-Lite bridges
or the separately tested memory crossbar. Behavioral targets do not prove
physical HBM/DDR controller or PHY behavior.

## Next integration sequence

1. Connect real CPU/SRAM ports and upstream protocol/width adapters to the
   already generated local data/config FlooNoCs, preserving cold boot.
2. Attach PULP iDMA frontends, CSRs and data ports; verify programmed copies.
3. Attach the actual memory target crossbar to the memory-local NoC and
   verify both global memory ingress paths against distinct memory targets.
4. Expand the existing connected NoC DUT for real CSR logic and AXI-Lite
   bridges, fairness/congestion, reset-during-traffic and interrupt checks.
5. Integrate real controller models/PHY environments in their proper scopes,
   then demonstrate CPU-programmed DMA transfers through full `soc_top`.
6. Extend scaling coverage. Extra compute profiles are generated today;
   a second memory subsystem requires generator support, not just a YAML edit.

## Acceptance gates and present limits

- Every declared route in a scope must complete against the intended target.
- Independent storage/readback checks validate data and B/R responses.
- AXI bursts, byte strobes, IDs and bounded stalls must be exercised; a pass
  covers the stimulus run, not maximum theoretical capacity or AXI compliance.
- Negative mutations must fail for the intended reason; empty/skipped cocotb
  runs cannot count as passes.
- Sparse crossbar denied paths return DECERR. Unmapped FlooNoC addresses
  instead assert upstream `DecodeError`; mapped slave faults test SLVERR.
- Every regression has a finite timeout, reproducible directed stimulus and
  retained diagnostics. Current-source CI must pass before merge.
- Xezim executes boot/memory/SRAM/SERV and compiles all eight NoCs. Verilator
  runs the connected NoC traffic test. Xezim NoC traffic remains unverified.
- The simulator binary is pinned separately; HDL changes do not rebuild Xezim.

See [implementation status](implementation-status.md) for integration limits
and [super-NoC verification](supernoc-verification.md) for commands and evidence.
