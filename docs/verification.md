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

The executable build/test catalog is [regression YAML](../config/regression.yaml);
[Bender source sets](../Bender.yml) replace per-test shell file arrays.
See [build and regression commands](regression.md) for the full suite,
filelist inspection, stage separation and retained results.

## Implemented scopes

| Scope | RTL under test | Checks |
| --- | --- | --- |
| Generator/configuration | SoC schema, addresses, backends and generators | Determinism, invalid configurations rejected, generated-file drift |
| Memory fabric | Verilog-AXI 2×2 crossbar and HBM/DDR behavioral targets | Default/full/sparse routes, responses, IDs, burst data and denied-path DECERR |
| Negative memory check | Same crossbar with a corrupted expectation | Must fail with the intended `FAIL AXI read` diagnostic |
| Local SRAM | Existing reusable dual-port SRAM test model | Uninitialized power-up, byte strobes and both ports |
| SERV execution | Real SERV and standalone Wishbone RAM | Three instructions execute and store the checked signature from a four-word image |
| CPU cold boot | PicoRV32/SERV, ROM, flash, blank SRAM and reset MMIO | CPU0 copies both programs through bus stores, releases CPU1 and both produce signatures; default and relocated address maps |
| Chip boot configuration | Real CPUs, shared NoCs, upstream WB/AXI/SRAM/reset and AXI memory stand-ins | CPU0-driven cold boot and init/run/check, every CPU greeting/peer check, missing-CPU negative, HBM/DDR model readback |
| Connected NoC BFM | All eight real FlooGen data/config meshes | All 28 mapped source/window routes, intended storage, concurrent reused IDs with distinct stream payloads, bursts, byte guards, stalls, SLVERR and corruption detection |

The CPU fetch smoke is a request-only diagnostic included in `full` and
CI diagnostics. [Boot details](boot.md) distinguish real instruction execution
from request-only smoke checks. The connected NoC scope uses AXI BFMs at
real endpoint boundaries; it does not attach CPUs, iDMA, AXI-Lite bridges
or the separately tested memory crossbar. Behavioral targets do not prove
physical HBM/DDR controller or PHY behavior.

## Next integration sequence

The [chip boot configuration](full-chip-boot.md) now attaches the CPUs,
SRAM, upstream protocol/width adapters, reset registers and target crossbar.
Keep the existing independent memory/boot/NoC scopes for fault isolation.

1. Attach real PULP iDMA frontends/CSRs/data ports and verify CPU-programmed copies.
2. Add real controller register maps, ready/interrupt behavior and physical
   controller/PHY models in their proper scopes.
3. Extend the chip scope with congestion/fairness, reset during traffic,
   interrupts and a portable C runtime/BSP as application tests grow.
4. Establish Xezim functional NoC/chip execution; compile-only probes stay
   separate from Verilator's routed-traffic proof.

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
- The SRAM target also runs with `-D SYNTHESIS` to preserve registered
  reads under synthesis guards. This is functional simulation, not synthesis.
- The simulator binary is pinned separately; HDL changes do not rebuild Xezim.

See [implementation status](implementation-status.md) for integration limits
and [super-NoC verification](supernoc-verification.md) for commands and evidence.
