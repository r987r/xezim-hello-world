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
| Ethernet and PCIe | Independent opt-in tests plus combined Ethernet→real DDR→iDMA→PCIe host BAR-pull/GMII TX smoke and separate PCIe endpoint-host DMA | One-run accepted AXI/TLP/GMII/DFI and checked bytes for the combined smoke; **not** a chained Ethernet→endpoint host-RAM DMA or full coverage matrix |

```sh
make check-config
make check-generated
make test-list
python3 tools/regress.py <target> --stage files
python3 tools/regress.py <target>
```

Every scoped regression must have a bounded timeout, independent data/readback checks, source-qualified failure semantics and retained diagnostic artifacts. A deliberate negative passes only when its **specific** named error occurs. Xezim runs standalone CPU/memory and structural NoC compilation; routed connected-NoC and current full-chip functional evidence is Verilator/Cocotb. An expected ID capacity is not measured utilization.

## Selected plans, scenarios and run evidence

A selected test records `selected-test-plan.json`, immutable source/config and command plan, `runner-events.json`, canonical `simulator/config_target/testname/run_id` and per-run result. The checked-in [stimulus catalog](../config/stimulus/tests.yaml) describes all 28 selected tests without fabricating evidence. The two SCN-2 CPU/BFM tests execute one source-resolved typed action DAG. Other existing C/Python/SV test drivers still have explicitly tracked legacy internal stimulus; **planned** INIT/RUN/CHECK descriptions and observed phase milestones are not universally source-dispatched per-action evidence. Full adapter migration is tracked under active P0 [#152](https://github.com/r987r/xezim-hello-world/issues/152); completed #119 established a partial foundation, not universal dispatch.

`variant-connectivity.json`, `variant-topology.json` and `variant-chip-manifest.json` describe source-selected opt-in RTL and monitor attachments. The same selected test may include original `axi-transactions.json`, `protocol-transactions.json`, `test-flow.json` and DFI events. Real **accepted** AW/W/B, AR/RLAST, TLP completion and matched expected bytes are a different evidence class from generated manifest/Slang CST paths. Port/bit elaborated proof remains [#46](https://github.com/r987r/xezim-hello-world/issues/46).

Passive monitors must start before the DUT clock, retain true IDs even when remapped across meshes, fail on incomplete captures where required, and never drive an active response pin. Test Runs and Fabric Explorer may show a plan before simulation but must label absent evidence **unmeasured**, not infer a PASS. See [publication](publication.md) and [test-flow evidence](test-flow.md).

## Integration boundary

The source-selected `chip-ethernet-ddr-pcie` combined target has **already** checked real Ethernet GMII/DMA → LiteDRAM/behavioral DFI → CPU0/iDMA → PCIe host **BAR pull** and Ethernet TX in a single simulation ([merged #150](https://github.com/r987r/xezim-hello-world/pull/150), [combined CI](https://github.com/r987r/xezim-hello-world/actions/runs/42498075763)). Separately, `chip-pcie-outbound` qualifies CPU-owned endpoint MWr/MRd to modeled host RAM ([merged #149](https://github.com/r987r/xezim-hello-world/pull/149)); those separate runs do **not** establish chained Ethernet → host-RAM DMA. The [post-MVP flow matrix #158](https://github.com/r987r/xezim-hello-world/issues/158) and P0 [source-selected action runtime #152](https://github.com/r987r/xezim-hello-world/issues/152) own extensions; CPU IRQ, fast Ethernet bypass, PHY and real HBM remain separate.
