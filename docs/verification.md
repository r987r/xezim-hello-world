# Verification scopes and source-of-truth

`config/soc.yaml` declares subsystem/address/interface architecture, `config/regression.yaml` selects the executable build and simulator profile, `Bender.yml` resolves RTL files, and `gen/verification/plan.json` plus `gen/supernoc/manifest.json` are generated source-derived outputs. There is **one** architecture diagram and **one** run/report pipeline. A configured or parsed link does not qualify elaborated bit-level connectivity or accepted traffic.

## Independent scopes

| Scope | What runs | What a PASS proves |
| --- | --- | --- |
| Memory fabric | Real Verilog-AXI crossbar with bounded modeled HBM/DDR targets | Routes, bursts, IDs, data, sparse reachability and expected errors |
| SRAM | Standalone dual-port model and `SYNTHESIS`-define mode | Legal byte strobes, registered reads, no implied silicon macro |
| CPU and cold boot | SERV and PicoRV32, standalone ROM/flash→uninitialized SRAM | Actual code fetch/store, reset MMIO, both CPU completion signatures |
| SuperNoC | Twelve upstream FlooGen local/global Data/Config meshes, Cocotb AXI agents | Routed endpoint read/write, ordering/stalls/error routes with **modeled** targets |
| Full-chip boot | Real dual CPUs/NoC/SRAM/reset, modeled HBM/DDR | CPU0 coordinated INIT/RUN/CHECK and host-checker model readback |
| PULP iDMA | Standalone, dual-engine BFM and CPU0 C-driven variants | Source-selected real DMA RTL and completed AXI/descriptor/readback in each independently tested configuration |
| Real DDR | Opt-in LiteDRAM AXI/controller, behavioral DFI/BankModel | Config-NoC initialization and CPU/iDMA readback; **not** physical DDR PHY |
| Ethernet and PCIe | Separate real packet/queue/bridge opt-in variants | GMII, accepted AXI/TLP, bytes, CQ/host BAR in each independent run, **not** a combined Ethernet→real DDR→PCIe run |

```sh
make check-config
make check-generated
make test-list
python3 tools/regress.py <target> --stage files
python3 tools/regress.py <target>
```

Every scoped regression must have a bounded timeout, independent data/readback checks, source-qualified failure semantics and retained diagnostic artifacts. A deliberate negative passes only when its **specific** named error occurs. Xezim runs standalone CPU/memory and structural NoC compilation; routed connected-NoC and current full-chip functional evidence is Verilator/Cocotb. An expected ID capacity is not measured utilization.

## Selected plans, scenarios and run evidence

A selected test records `selected-test-plan.json`, immutable source/config and command plan, `runner-events.json`, canonical `simulator/config_target/testname/run_id` and per-run result. The two SCN-2 CPU/BFM tests execute one source-resolved typed action DAG. Other existing C/Python/SV test drivers still have explicitly tracked legacy internal stimulus; **planned** INIT/RUN/CHECK descriptions and observed phase milestones are not universally source-dispatched per-action evidence. Full adapter migration is tracked under [#119](https://github.com/r987r/xezim-hello-world/issues/119).

`variant-connectivity.json`, `variant-topology.json` and `variant-chip-manifest.json` describe source-selected opt-in RTL and monitor attachments. The same selected test may include original `axi-transactions.json`, `protocol-transactions.json`, `test-flow.json` and DFI events. Real **accepted** AW/W/B, AR/RLAST, TLP completion and matched expected bytes are a different evidence class from generated manifest/Slang CST paths. Port/bit elaborated proof remains [#46](https://github.com/r987r/xezim-hello-world/issues/46).

Passive monitors must start before the DUT clock, retain true IDs even when remapped across meshes, fail on incomplete captures where required, and never drive an active response pin. Test Runs and Fabric Explorer may show a plan before simulation but must label absent evidence **unmeasured**, not infer a PASS. See [publication](publication.md) and [test-flow evidence](test-flow.md).

## Integration boundary

The next *separate* combined target must source-select **real Ethernet GMII/DMA, real LiteDRAM/DFI, CPU/iDMA and PCIe host BAR pull in the same simulation**, then independently check payload and completion at every boundary. This is not delivered by concatenating independent artifacts. The test is specified in [combined acceptance](multiprotocol-integration-readiness.md) and [epic #34](https://github.com/r987r/xezim-hello-world/issues/34); PCIe outbound host-memory DMA, CPU ISR, fast Ethernet bypass and real HBM are outside the first functional smoke.
