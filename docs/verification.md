# Hierarchical SoC verification

The architecture in `config/soc.yaml` is the source of truth for subsystem
instances, network boundaries, address maps and IP implementation choices.
`tools/socgen.py` validates it and generates simulation metadata and an HBM
fabric test harness. Tool and vendor revisions are recorded in
`config/ip.lock.yaml` and `toolchains/xezim.env`.

## Scopes and status

| Scope | DUT / planned boundary | Status |
|---|---|---|
| HBM fabric | Real AXI4 2x2 crossbar, two independent AXI RAM models, two master BFMs | Implemented; run `make dv-hbm` |
| Local data NoC | Local compute crossbar; CPU/DMA boundary BFMs | Planned |
| Local config NoC | AXI4-Lite crossbar and CSR models | Planned |
| Compute subsystem | Local NoCs + actual DMA, synthetic remote endpoints | Planned |
| Global data NoC | Compute ingress/egress and HBM data boundary | Planned |
| Global config NoC | Remote CSR accesses between subsystems | Planned |
| Full chip | Both compute subsystems, memory subsystem, two global networks | Planned |

"Implemented" describes code checked in, not a claim that a particular simulator
has passed it; the GitHub Actions badge/logs show actual results.

## HBM test

The first suite uses the pinned upstream `verilog-axi` **AXI4** crossbar as the
real fabric DUT. AXI RAMs act as protocol-correct memory endpoints, not physical
HBM controllers/PHYs. Their backing memory is deliberately small and should not
be confused with the configured HBM address windows.

For each ingress and each HBM target, the corresponding master BFM performs a
4-beat INCR write followed by a 4-beat read and compares the result against an
independent deterministic data function. The passive route monitor checks AXI
address routing, crossbar-expanded source IDs, and that **every** ingress-target
pair completed read and write address handshakes. The negative regression changes
one expected read value and must fail for a `FAIL AXI read` mismatch.

### Run

```sh
python3 -m pip install PyYAML==6.0.3
make check-config
XEZIM_BIN=/path/to/xezim make dv-hbm
```

The runner fetches the pinned crossbar RTL source once, regenerates the harness,
and invokes the existing Xezim binary; **it never builds Xezim or Rust**.

### Scaling and swapping IP

Add compute instances to `config/soc.yaml`; every scope reads the same canonical
instance names and address map. Change HBM ingress/controller counts and update
explicit address windows plus the VIP ingress count; the HBM harness is generated
for the new dimensions. Changing third-party RTL means updating the lockfile and,
if its ports differ, the fabric adapter/port mapper. YAML alone does **not** make
arbitrary third-party IP plug-compatible.

## Verification progression

1. HBM local fabric: route and data integrity for all ingress-target pairs.
2. Compute local NoCs and a real DMA (iDMA is a candidate); drive CPU-like MMIO
   and DMA traffic through passive AXI monitors.
3. Independently verified global data and config NoCs with synthetic endpoints.
4. Full-chip SoC: compose existing passive agents and scoreboards, synchronize
   DMA0/DMA1 cross-HBM transfers, inject congestion, and prove control-plane
   forward progress under data-plane load.
5. Add full CPU RTL and software after the fabric is stable.

Future testbenches should reuse common agents/checkers rather than instantiate
multiple `run_test()` contexts. Every suite must use finite simulation timeouts,
seeded stimulus, nonzero transaction counts and a negative test that proves a
checker can detect an error.
