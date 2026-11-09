# Real combined hardware source-rebuild qualification (#184)

This is not a second separate CI pipeline. The existing [single-chip real
Ethernet+DDR+iDMA+PCIe integration workflow](../.github/workflows/dv-combined34.yml)
installs pinned FlooNoC, LiteDRAM, LiteX, PCIe and CPU toolchains, generates
the actual selected full-chip source and runs real integration tests.

Its pre-simulation step now runs the same exact source archive twice:
first `regress.py chip-ethernet-ddr-pcie --stage files`, then
`stage_selected_rtl.py --profile chip-ethernet-ddr-pcie`, and finally
`build_hardware_variant.py --profile chip-ethernet-ddr-pcie --check`.
The last step executes the *real selected-source generator again*, into
temporary review staging, and rejects different selected SystemVerilog,
firmware image, NoC collateral or compiler filelist/source closure. This
is followed by the workflow's original `make check-generated`, actual
combined chip compile and passive evidence checks.

A passing source replay establishes that *that exact CI checkout* can
regenerate the selected source inputs with pinned tools. It is not by
itself a protocol PASS or a checked-in combined `gen/projects` output;
the existing live combined simulation gate is still required and #184
must still teach the atomic generator to own selected combined outputs.
The CI archive of verified review source is available to inspect after
a successful or failed run, with provenance preserved even when test
execution later fails.
