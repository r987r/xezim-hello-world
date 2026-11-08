# Documentation index

The [root README](../README.md) contains setup and the single generated whole-chip topology. **Build and hardware configuration are defined by source, not by this index.** See the [live Test Runs site](https://r987r.github.io/xezim-hello-world/) for executed evidence; [GitHub issues](https://github.com/r987r/xezim-hello-world/issues) own progress, outstanding work, and historical investigations.

| Need | Guide / authority |
| --- | --- |
| Build, choose a test, run locally | [Regression](regression.md), [simulator compatibility](simulator-compatibility.md), [naming](test-identity.md) |
| Configure subsystems and replace IP | [Architecture](architecture.md), [interface budgets](../config/interface_contracts.yaml), [IP portability](ip-portability.md) |
| Testbench scope and stimulus | **[P0 scalable action runtime](scalable-stimulus-runtime.md)**, [Verification](verification.md), [authored test YAML](../config/stimulus/tests.yaml), [scenario actions](scenario-contract.md), [test-flow evidence](test-flow.md), [P0 runtime #152](https://github.com/r987r/xezim-hello-world/issues/152) |
| Review CI evidence | [Pages/publication](publication.md), [AXI reports](axi-run-reports.md), [protocol reports](protocol-run-reports.md), [Fabric Explorer](design-explorer.md) |
| CPU boot and DMA | [Boot](full-chip-boot.md), [DMA](dma-bringup.md), [memory allocation](memory-allocation.md) |
| PCIe and Ethernet | [PCIe host](pcie0-host-phases.md), [Ethernet MVP](ethernet0-closure-gate.md) |
| DDR and registers | [DDR model/RTL](../rtl/memory/ddr4/README.md), [CSR ownership](csr-generation.md), [CSR source coverage](csr-source-coverage.md) |
| Combined test and remaining flow matrix | [Verified functional MVP and boundaries](integration-closure-34.md), [combined acceptance](multiprotocol-integration-readiness.md), [post-MVP flow matrix #158](https://github.com/r987r/xezim-hello-world/issues/158) |

Audit local Markdown links with `make check-docs` (also run by check-config and Pages CI).

New contributors: read [AGENTS.md](../AGENTS.md). Never edit `gen/` or the generated section of README directly; use `make gen` and `make check-generated`. Documentation describes interfaces and reproducible behavior, **not** the last PR's status.
