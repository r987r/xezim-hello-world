# Reuse upstream AXI-Lite bridges across FlooNoC

## Decided interface boundary (do not reinvent)

FlooNoC's [upstream AXI4 generator](https://github.com/pulp-platform/FlooNoC/tree/05368bdff914f91a48b47c4ceddfc6ff266c6b3a/floogen)
declares `protocol: AXI4`. **It is not an AXI4-Lite native transport**.
Separate global and local configuration NoCs use 32-bit AXI4 wire ports,
but exchange *AXI4-Lite semantics* (single-beat, no bursts, no ATOPs) at
the real end-device boundaries.

```text
CPU/CSR AXI4-Lite manager
  -> upstream PULP axi_lite_to_axi
  -> local_config FlooNoC AXI4 endpoint
  -> global_config FlooNoC AXI4 endpoint (when remote)
  -> remote subsystem local_config FlooNoC
  -> upstream PULP axi_to_axi_lite
  -> actual DMA / reset / controller CSR AXI4-Lite subordinate
```

**Reuse exact pinned upstream modules; do NOT write adapters or a custom
AXI4-Lite NoC:**

- [`axi_lite_to_axi.sv`](https://github.com/pulp-platform/axi/blob/70b8e54fd460e3308e58be596ceb3566a6e3576e/src/axi_lite_to_axi.sv):
  drives an AXI4 manager from an AXI-Lite request; assign upstream ID,
  sidebands and cache fields as required by its documented ports.
- [`axi_to_axi_lite.sv`](https://github.com/pulp-platform/axi/blob/70b8e54fd460e3308e58be596ceb3566a6e3576e/src/axi_to_axi_lite.sv):
  converts AXI4 request/response semantics to AXI-Lite at the final CSR.
  **Do not** simply drop AXI ID, LEN, LAST, or user fields.
- [`axi_lite_dw_converter.sv`](https://github.com/pulp-platform/axi/blob/70b8e54fd460e3308e58be596ceb3566a6e3576e/src/axi_lite_dw_converter.sv):
  existing width adaptation when a future CSR width differs from the
  chosen 32-bit control plane.
- Upstream standalone examples/testbenches:
  [`tb_axi_lite_to_axi.sv`](https://github.com/pulp-platform/axi/blob/70b8e54fd460e3308e58be596ceb3566a6e3576e/test/tb_axi_lite_to_axi.sv),
  [`tb_axi_to_axi_lite.sv`](https://github.com/pulp-platform/axi/blob/70b8e54fd460e3308e58be596ceb3566a6e3576e/test/tb_axi_to_axi_lite.sv),
  and the [PULP AXI README](https://github.com/pulp-platform/axi/tree/70b8e54fd460e3308e58be596ceb3566a6e3576e).
- For *native* AXI4 on the NoC, upstream
  [`floo_axi_chimney.sv`](https://github.com/pulp-platform/FlooNoC/blob/05368bdff914f91a48b47c4ceddfc6ff266c6b3a/hw/floo_axi_chimney.sv)
  uses `floo_pkg::ChimneyDefaultCfg`. Xezim generates parameter
  bindings for MaxTxns, MaxUniqueIds, MaxTxnsPerId, RRoBType/RRoBSize
  and BRoBType/BRoBSize, without modifying third-party router RTL.

### End-to-end checks needed before calling control NoC functional

Use the **global_config** and full **compute/memory subsystem** TBs,
not a new separate testbench for each adapter.

* Remote and local CSR read/write, correct data, byte strobes and errors.
* Single-beat AXI4 (AWLEN/ARLEN == 0; WLAST asserted) across the NoC,
  proper per-request ID handling and response return.
* AW/W timing decoupling, read/write overlap and bounded backpressure;
  no deadlock when data NoC carries concurrent DMA requests.
* Address resolution: compute0 DMA at 0x40000000, compute1 DMA at
  0x40010000, boot.reset_ctrl at 0x40020000 and reserved
  memory0.ctrl at 0x40030000.
* At least two independent routers in the global config network,
  plus local configuration FlooNoC hops, exercised with real RTL.

**Status:** the config network's upstream structural SystemVerilog is
generated and tracked under `gen/noc/floonoc/`; bridge endpoint
instances, elaboration and CSR transaction checks remain TODO.
The 0x40030000 memory controller register aperture is reserved
only. It is not yet a working controller.

## Dependencies

Use the top-level [FlooNoC Bender.yml](https://github.com/pulp-platform/FlooNoC/blob/05368bdff914f91a48b47c4ceddfc6ff266c6b3a/Bender.yml)
to resolve the upstream AXI/common_cells/FlooNoC package versions and
include paths. Xezim `config/ip.lock.yaml` pins the FlooNoC generator
revision; avoid hand-selected incompatible versions of its dependencies.

Pin in the architectural manifest and validate *every* contract change.
Note that an RTL generator succeeding is not proof a network compiles,
elaborates or passes transactions.
