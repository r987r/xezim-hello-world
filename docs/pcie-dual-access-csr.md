# PCIe dual-access CSR ownership (P0 #76)

## Two independent front doors, shared underlying hardware state

There are **two address domains**, not a BAR window aliased onto CPU
physical addresses. Neither Root Complex nor testbench is allowed to
program the other participant through hidden shared control wires.

| Function | CPU0 DBI, Config NoC | Host PCIe Type-0 config | Authoritative writer |
| --- | --- | --- | --- |
| Existing outbound requester descriptors | `pcie0.ctrl+0x0000..0x003f` | **Unmapped** | CPU0 |
| Advertised BAR0 aperture (bytes) | `+0x1000` RW before COMMIT | BAR0 sizing probe via `0x10` | CPU0 pre-link |
| Local SoC SRAM target | `+0x1004` RW before COMMIT | **Not exposed** | CPU0 pre-link |
| COMMIT / START | `+0x1008` write-one pulses | **Not exposed** | CPU0, guarded policy |
| Commit and readiness status | `+0x100c` RO | **Not exposed** | Hardware |
| Host-assigned BAR0 PCI bus base | `+0x1010` RO **hardware alias** | `0x10` BAR0 RW/probe | Host over link |
| Host COMMAND.Memory Space Enable | `+0x1014` RO **hardware alias** | `0x04` COMMAND bit 1 | Host over link |
| PHY / LTSSM / NoC status | `+0x1018` RO | Standard capabilities, separately sourced | Hardware |

CPU0 `pcie0.ctrl` begins at **0x40040000** as configured by
`config/soc.yaml`: the device DBI alias addresses are
**0x40041010** for host-assigned BAR0 and **0x40041014** for MSE.
Those numbers are **not host BAR addresses**; the host may assign
BAR0 to e.g. **0x80001000**. The real local SRAM address is
**0x12000000**. These are three distinct address domains.

### State ownership, not duplicate registers

1. CPU0 sets size and local target and issues COMMIT before endpoint
   LTSSM startup. Hardware validates the aperture, bounds, alignment
   and write freeze. A host cannot access the device's Config NoC.
2. Independently, the Root Complex trains the link and uses actual
   ConfigWr0/ConfigRd0 TLPs to probe the advertised aperture, assign
   the PCI bus BAR0 and enable COMMAND.MSE. The pinned original
   OpenPCIe configuration responder owns `host_bar0_bus_base_o`
   and `host_memory_enable_o` **once**.
3. The device DBI `host_bar0` and `host_command` are hardware-
   supplied read-only mirrors of those very same signals.
   CPU writes to either address must fail, never alter the host
   assigned BAR0 or COMMAND. CPU0 may read the state for enumeration/
   initialization handshakes but may not make host-controlled changes.
4. Memory accesses are additionally gated on device BAR COMMIT,
   endpoint link, selected NoC readiness and host MSE. L0 alone
   does not qualify SRAM traffic.

## Source ownership and current implementation status

- Project CPU-side field/offset/permissions: one RDL,
  `csr/rdl/pcie_endpoint_prelink_ctrl.rdl`. Uses `swwe` for
  hardware-controlled prelink write freeze and `singlepulse`
  for one-cycle COMMIT/START. Its RO aliases use `sw=r; hw=w`
  so the generated bank must receive actual original host-owned
  values via the PeakRDL `hwif_in`, not from duplicated software state.
- `tools/pcie_csrgen.py` pins the same SystemRDL/PeakRDL package versions
  as `tools/csrgen.py`, enforces nonoverlap with the live outbound
  requester, exports AXI4-Lite RTL, C offsets/masks and the catalog,
  and checks exact deterministic regeneration. The PCIe Actions
  `pcie-csr-generation` job tests the source in isolation; it does
  **not** prove a connected CPU0, successful MMIO or firmware use.
- The original host-visible Type-0 configuration space is upstream
  `src/pcie_cfg/pcie_config.rdl` plus its PeakRDL register block.
  `dv/pcie_link/pcie_bar0_host_cfg.sv` is a **temporary host-path
  protocol overlay** for BAR0 probe, MSE and host address assignment
  until the vendor RDL and proper DBI hardware interface are reconciled.
  This custom protocol behavior is not normal software CSR storage.
- `dv/pcie_link/endpoint_prelink_ctrl.sv` remains a **test-only
  direct-write surrogate**; it now decodes RDL-relative offsets
  `0x1000..0x1018`, reads the actual BAR/MSE hardware outputs
  through two aliases and explicitly rejects CPU writes to those
  read-only addresses. This does not instantiate the generated RTL
  or synthesize a Config-NoC responder.
- `dv/pcie_link/tb_pcie_cross_link.sv` observes the *original*
  host-to-endpoint config TLP path and separately confirms the
  device DBI read alias equals the original host BAR and MSE. No
  host/device sideband is used to assist LTSSM or PCIe configuration.

## Remaining P0 integration gates — do not claim they passed

- [ ] Attach the generated PeakRDL AXI4-Lite bank as a real
  `pcie0.ctrl + 0x1000` responder. Preserve the already-working
  requester `0x0000..0x003f` frontdoor, arbitrate/decode subwindows,
  return real SLVERR/DECERR for illegal writes, and use upstream PULP
  AXI4↔AXI4-Lite adapters rather than invent a bridge
- [ ] Move project-owned DBI storage and COMMIT pulse generation out of
  the test-only direct-write surrogate, wire PeakRDL `hwif` to small,
  reviewed BAR/LTSSM validation logic; check reset/lock semantics
- [ ] Reconcile **host Type-0 RDL** BAR0/COMMAND writable semantics
  with the original OpenPCIe config responder so a source-generated
  bank—not an indefinitely maintained second overlay—exposes host state
- [ ] Compile actual CPU0 RV32I firmware using the RDL-generated header,
  program aperture/target/COMMIT/START *through real Config NoC*,
  and read back BAR0/MSE aliases after genuine RC enumeration. Capture
  passive AXI plus TLP source-linked evidence in existing test reports
- [ ] Commit/check selected generated RTL and firmware ABI under
  the repository's generator ownership (do not hand-edit `gen/`).
  A CI-only `.tools/pcie-csr/` artifact is **not** that acceptance.

This scoped RDL/register work is part of [PCIe P0 #76](https://github.com/r987r/xezim-hello-world/issues/76)
and the general [CSR firmware ABI #90](https://github.com/r987r/xezim-hello-world/issues/90).
The original `chip-pcie-host` / `chip-pcie-outbound` modeled TLP
regressions remain default; the real Gen1 link is opt-in.
