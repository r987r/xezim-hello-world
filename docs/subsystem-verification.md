# Verification scopes and remaining integration

All local/global data/config networks use pinned upstream FlooNoC.
The chip boot configuration attaches a 1×2 Verilog-AXI target crossbar;
the older 2×2 memory stress scope remains independent.
FlooNoC's config transport is 32-bit AXI4; CSR-facing AXI4-Lite requires
upstream PULP `axi_lite_to_axi` and `axi_to_axi_lite` adapters.
See [implementation status](implementation-status.md) for the current
inventory and [super-NoC verification](supernoc-verification.md) for the
single connected BFM test's coverage and results.

| Scope | Current behavior or next substantive milestone |
| --- | --- |
| `memory_tb` | Real Verilog-AXI 2x2 crossbar, independent HBM/DDR behavioral windows, full/sparse route tests |
| `boot_tb`, SRAM and SERV checks | Preserve real two-core cold boot, no SRAM preload, independent bring-up checks |
| `supernoc_tb` | One generated wrapper, all eight real meshes, upstream AXI agents, local/remote reads/writes and stress/error checks |
| compute0 boot configuration | PicoRV32/SRAM/upstream adapters connected; optional real iDMA/CSR generated for DMA test mode |
| compute1 boot configuration | SERV/Wishbone/AXI adaptation and SRAM connected; optional real iDMA generated for DMA test mode |
| config endpoints | CPU/reset AXI-Lite boundaries connected; DMA CSR bridge generated in DMA mode; controller registers pending |
| memory boot configuration | Local NoC attached to target crossbar and AXI slave models; both global memory ingress links retained |
| full-chip boot | Real CPUs coordinate init/run/check; upstream AXI BFM checks HBM/DDR stand-ins; generated SS0/SS1 DMA and CSR connections passed the full-chip NoC RTL traffic test ([CI 41885417960](https://github.com/r987r/xezim-hello-world/actions/runs/41885417960)); CPU DMA firmware and physical controllers pending |

Do not add another testbench per bridge, router or simulator issue.
Extend the one integrated NoC DUT and the substantive subsystem scopes.
The existing boot/SRAM checks remain independent for fault isolation.

## Interface capacity and simulator limits

`config/interface_contracts.yaml` validates AXI widths, IDs, pending
read/write budgets, burst sizes and native chimney/RoB parameters.
A traffic pass covers its actual stimulus, not every possible parameter
combination or the maximum theoretical capacity. Data RoBs use
`MaxTxnsPerId=9` for a budget of eight because pinned upstream counter
widths disagree at power-of-two depths. Never patch vendor RTL or hide
assertions to avoid that guard. Target-only chimneys use native `NoRoB`;
initiator chimneys retain their configured RoBs. ATOPs remain disabled.

Verilator runs the NoC traffic regression. Xezim compiles all eight
meshes and runs the independent CPU/memory checks; it has no verified
NoC transaction path yet. Preserve diagnostics in
[simulator compatibility](simulator-compatibility.md).

Unmapped NoC accesses assert upstream `DecodeError`; they are not yet
handled as recoverable DECERR. The NoC BFM error test injects mapped
slave faults and checks propagated SLVERR. Sparse crossbar DECERR tests
remain a separate scope. Real HBM/DDR timing, PHYs, coherency, CPU-triggered DMA/interrupt firmware,
reset-during-traffic and UVM VIP integration remain future work.
