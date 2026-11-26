# Real combined hardware source-rebuild qualification (#184)

This is not a second separate CI pipeline. The existing [single-chip real
Ethernet+DDR+iDMA+PCIe integration workflow](../.github/workflows/dv-combined34.yml)
installs pinned FlooNoC, LiteDRAM, LiteX, PCIe and CPU toolchains, generates
the actual selected full-chip source and runs real integration tests.

Before simulation, `regress.py chip-ethernet-ddr-pcie --stage files`
creates a distinct source-only run directory. Each review CLI is given that
exact `--files-workspace` (the parent of the printed `sources.f`). The
rebuild command, `build_hardware_variant.py --profile chip-ethernet-ddr-pcie --check`,
prepares a second workspace and verifies source equivalence against the
first one's staged manifest. `make check-generated-combined` independently
prepares a third workspace and compares the portable checked-in RTL
and all collateral byte for byte. Neither step promotes a source-only
workspace to runtime evidence. Portable Verilator lint and the original
combined chip compile and passive evidence checks run separately.

A passing source replay establishes that *that exact CI checkout* can
regenerate the selected source inputs with pinned tools. It is not by
itself a protocol PASS or a checked-in combined `gen/projects` output;
the existing live combined simulation gate is still required and #184
must still teach the atomic generator to own selected combined outputs.
The CI archive of verified review source is available to inspect after
a successful or failed run, with provenance preserved even when test
execution later fails.
