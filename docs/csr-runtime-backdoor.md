# Runtime CSR back-door binding contract (issue #91)

`tools/csr_runtime.py` provides a **read-only** bridge from logical instance/register/field identities into visible simulator HDL handles. It builds upon `tools/csr_backdoor.py` and **never** derives or embeds physical hierarchy directly from portable SystemRDL. The register model is composed from per-IP definitions and SoC instance mapping. Physical signal paths are exact-build evidence supplied by the simulator adapter.

## Runtime safety contract

- `discover(dut, variant, build_sha256, simulator, requested_paths)` resolves actual HDL handles (currently Verilator/Cocotb-compatible), checks the actual top name, object bit width and 64-hex-character build fingerprint, and reports missing/optimized-away paths as unavailable by default. Use `strict=True` to fail a required binding immediately.
- Two disjoint logical fields may occupy the same real RTL word; `bind()` rejects overlapping physical bits, stale variants, invalid widths and unsupported policies.
- `SafeCsrBackdoor.read(logical_path)` accepts **only** fields explicitly declared `backdoor_read_only` and bound to actual simulator-visible handles. `write()` unconditionally raises `BindingError`. No direct deposit replaces a W1C, doorbell, IRQ acknowledgement, FIFO or AXI write.
- The output qualification deliberately says **runtime visible**, not proven register flop. A visible output or temporary combinational wire is not automatically authoritative storage. A later integration test must prove the field has the same value as a real frontdoor register read at the proper sampled phase.
- Reading a backdoor handle is not an AXI transaction and must not increase frontdoor coverage. The existing passive AXI report is authoritative for accepted requests/responses.

## Evidence and next integration

The focused test `python3 tools/run_csr_runtime_probe.py` uses real Verilator/Cocotb to resolve a test-only registered signal through a hierarchy, read field slices and reject writes, missing paths and frontdoor-only fields. **This is not a real reset-controller/Config-NoC test** and does not qualify Xezim access.

Next, bind to the actual elaborated PeakRDL reset-control RTL on #86 with an explicitly safe read-only field and compare values against CPU/AXI reads after correct ordering and quiescence. For Xezim, implement a separate VPI/DPI adapter using only verified exposed handles, not guessed names. Bulk SRAM/DDR/HBM backdoor services remain owned by issue #39; stimulus scenarios remain issue #79.
