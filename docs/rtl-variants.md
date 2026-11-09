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

Other selected RTL variants have already been archived and hashed under
each test's `.tools/regression/<target>/selected-rtl/` and published as CI
artifacts (#163). Review snapshots for those test-independent hardware
combinations require a reproducible generation/qualification contract and
actual source bytes. Never relabel the default top as the combined one, or
treat a manifest as elaboration/protocol proof. #163/#165 will track the
remaining generated variant promotion.

The default generator's source/IR/IP contract acceptance remains governed by
the canonical IR (#165/#166); byte-level elaboration proof belongs to #46.
