# Reuse upstream AXI-Lite bridges across FlooNoC

## Decided interface boundary (do not reinvent)

FlooNoC's [upstream AXI4 generator](https://github.com/pulp-platform/FlooNoC/tree/05368bdff914f91a48b47c4ceddfc6ff266c6b3a/floogen)
declares `protocol: AXI4`. **It is not an AXI4-Lite native transport**.
Separate global and local configuration NoCs use 32-bit AXI4 wire ports.
The connected BFM regression sends single-beat, non-atomic AXI4 accesses.
The chip boot configuration attaches real CPU AXI4-Lite bridges and reset
CSR registers. DMA CSR endpoints are generator-wired in optional `DmaEnable=1` mode,
with upstream AXI-to-Lite register logic and 32-bit HEAD staging; controller
CSRs remain pending.

The chip boot path converts CPU AXI4-Lite through upstream `axi_lite_to_axi`,
traverses local/global/remote-local config FlooNoCs as needed, then converts
through upstream `axi_to_axi_lite` at the actual CSR subordinate.

The chip uses the AXI revision locked by FlooNoC's upstream `Bender.lock`,
without mixing it with the separately planned SoC PULP AXI revision below.
See [chip boot integration](full-chip-boot.md).

**Reuse exact pinned upstream modules; do NOT write adapters or a custom
AXI4-Lite NoC:**

- [`axi_lite_to_axi.sv`](https://github.com/pulp-platform/axi/blob/0ccc838fe06aeeb857eb83c6be9a915c4bf99566/src/axi_lite_to_axi.sv):
  drives an AXI4 manager from an AXI-Lite request; assign upstream ID,
  sidebands and cache fields as required by its documented ports.
- [`axi_to_axi_lite.sv`](https://github.com/pulp-platform/axi/blob/0ccc838fe06aeeb857eb83c6be9a915c4bf99566/src/axi_to_axi_lite.sv):
  converts AXI4 request/response semantics to AXI-Lite at the final CSR.
  **Do not** simply drop AXI ID, LEN, LAST, or user fields.
- [`axi_lite_dw_converter.sv`](https://github.com/pulp-platform/axi/blob/0ccc838fe06aeeb857eb83c6be9a915c4bf99566/src/axi_lite_dw_converter.sv):
  existing width adaptation when a future CSR width differs from the
  chosen 32-bit control plane.
- Upstream standalone examples/testbenches:
  [`tb_axi_lite_to_axi.sv`](https://github.com/pulp-platform/axi/blob/0ccc838fe06aeeb857eb83c6be9a915c4bf99566/test/tb_axi_lite_to_axi.sv),
  [`tb_axi_to_axi_lite.sv`](https://github.com/pulp-platform/axi/blob/0ccc838fe06aeeb857eb83c6be9a915c4bf99566/test/tb_axi_to_axi_lite.sv),
  and the [PULP AXI README](https://github.com/pulp-platform/axi/tree/0ccc838fe06aeeb857eb83c6be9a915c4bf99566).
- For *native* AXI4 on the NoC, upstream
  [`floo_axi_chimney.sv`](https://github.com/pulp-platform/FlooNoC/blob/05368bdff914f91a48b47c4ceddfc6ff266c6b3a/hw/floo_axi_chimney.sv)
  uses `floo_pkg::ChimneyDefaultCfg`. `tools/floonoc_gen.py` generates parameter
  bindings for MaxTxns, MaxUniqueIds, MaxTxnsPerId, RRoBType/RRoBSize,
  BRoBType/BRoBSize and disabled ATOP/atomic reservations, without modifying third-party router RTL.

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

**Status:** all config meshes are generated under `gen/noc/floonoc/`,
compile in Verilator and Xezim, and pass routed single-beat AXI4 BFM
read/write, byte-strobe, stall and SLVERR checks in Verilator. Actual
CPU AXI4-Lite bridge instances and the reset register bank also execute
in the chip boot scope; secondary CPUs acknowledge initialization through
the remote configuration path. DMA registers are generated and are verified by the separate `chip-dma`
regression once CI passes. Physical memory-controller registers remain pending.
The 0x40030000 memory controller register aperture is reserved
only. It is not yet a working controller.

## Dependencies

Use the top-level [FlooNoC Bender.yml](https://github.com/pulp-platform/FlooNoC/blob/05368bdff914f91a48b47c4ceddfc6ff266c6b3a/Bender.yml)
to resolve the upstream AXI/common_cells/FlooNoC package versions and
include paths. The links above use the AXI revision selected by that
FlooNoC's `Bender.lock` (`0ccc838...`); do not mix in the separate standalone
PULP AXI source pin from `config/ip.lock.yaml`. That file pins FlooNoC's
generator revision; its Bender lock owns the NoC dependency versions.

Pin in the architectural manifest and validate *every* contract change.
Note that an RTL generator succeeding is not proof a network compiles,
elaborates or passes transactions.
