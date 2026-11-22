# Reviewable SoC RTL build variants

For the default project, the real generated top is checked into two equivalent
locations:

- `gen/chip/soc_top.sv` — original default SoC generator output
- `gen/projects/xezim_soc_dv/variants/default/rtl/soc_top.sv` — stable
  project/variant review path, copied from the actual output by
  `tools/generate.py`

A SHA256 manifest is adjacent to the review copy. `make gen` and
`make check-generated` regenerate/check both paths **byte-for-byte**;
neither is hand-edited. The default review copy is not the opt-in
CPU-DMA / Ethernet / PCIe / DDR variant selected in a special regression.

The separate [combined Ethernet/DDR/PCIe review top](../gen/projects/xezim_soc_dv/variants/ethernet-ddr-pcie/rtl/soc_top.sv)
is tracked with its [source manifest](../gen/projects/xezim_soc_dv/variants/ethernet-ddr-pcie/manifest.json)
and [compiler order](../gen/projects/xezim_soc_dv/variants/ethernet-ddr-pcie/compiler/sources.f).
Use [`make check-generated-combined`](build-hardware-variant.md) for pinned
selected-source replay; the ordinary default check validates and preserves
the combined tree without rerunning its heavy toolchain.

Other selected builds may be available in their run output's `selected-rtl/`
archive and in matching CI artifacts. Never relabel the default top as the
combined one or treat a manifest as elaboration/protocol proof. #163/#165
track remaining provenance and variant promotion.

The default generator's source/IR/IP contract acceptance remains governed by
the canonical IR (#165/#166); byte-level elaboration proof belongs to #46.
