# Canonical SoC graph (incremental SoC-IR, #165)

The initial canonical schema is a **source-declared** stable graph built from
the existing authoritative config/soc.yaml and generated
gen/diagrams/noc-topology.json. This deliberately does not introduce another
RTL emitter, a replacement for Bender/FlooGen, or claims of live packet
engines or elaborated bit-level connectivity.

Run:

    python3 tools/soc_ir.py --out .tools/soc-ir/default.json
    python3 tools/soc_ir.py --out .tools/soc-ir/default.json --check
    python3 -m unittest tests.test_soc_ir -v

The source IR contains normalized subsystems, address apertures, buses,
fabric/backend declarations, named network outputs and generated router/NI
instances. Links use stable endpoint-derived identities rather than
noc_link_0001 presentation indexes. It contains evidence labels for source-only
topology and records missing elaboration and missing generator adoption
explicitly. Byte-identical repetition is a CI check. A mismatched SoC source,
duplicate physical route, missing endpoint or invalid address aperture fails
closed; the existing socgen validator remains the address/boot authority.

Next (separate PR stages): have one chosen generator consume this IR while
proving byte-identical output, introduce first named test-independent build
variant, then migrate remaining RTL/NoC/address/CSR/monitor emitters. Opt-in
Ethernet/PCIe/DDR compositions currently depend on legacy regress.py modes:
do not mislabel the initial default IR as the actual opt-in compiled RTL.
Related: #162, #163, #164, #166, #46, #152.
