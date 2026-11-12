#!/usr/bin/env python3
"""Audit actual linked RV32I firmware footprints across selected CSR variants.

This is compile/ABI evidence, NOT proof of real MMIO acceptance or a replacement
for the existing full-chip/PCIe/Ethernet simulations and AXI monitors.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import tempfile

import yaml

from tools.cpu_dma_firmware import ROOT, compile_firmware


MODES = (
    ("cpu_dma", {}),
    ("ethernet_cpu", {"ethernet_cpu_mode": True}),
    ("pcie_outbound_cpu", {"pcie_host_mode": True, "pcie_outbound_mode": True}),
)


def audit(config: Path) -> dict:
    config_bytes = config.read_bytes()
    cfg = yaml.safe_load(config_bytes)
    records = []
    with tempfile.TemporaryDirectory(prefix="csr-fw-footprint-") as scratch:
        work = Path(scratch)
        for mode, flags in MODES:
            legacy_dir = work / mode / "legacy"
            selected_dir = work / mode / "generated"
            # Compare production generated DMA and SoC-base CSR aliases against
            # the old DMA offsets and legacy command-line physical-base ABI.
            legacy = compile_firmware(
                cfg, legacy_dir, use_config_csr_header=False,
                use_legacy_dma_csr=True, **flags)
            generated = compile_firmware(cfg, selected_dir, **flags)
            old_bin = (legacy_dir / "cpu_dma.bin").read_bytes()
            new_bin = (selected_dir / "cpu_dma.bin").read_bytes()
            old_elf = legacy_dir / "cpu_dma.elf"
            new_elf = selected_dir / "cpu_dma.elf"
            if (old_bin != new_bin or legacy["hook"] != generated["hook"]
                    or legacy["sha256"] != generated["sha256"]):
                raise ValueError(f"{mode}: generated CSR changed real linked RV32I image")
            if not new_bin or len(new_bin) > generated["flash_limit"]:
                raise ValueError(f"{mode}: missing or oversized linked firmware")
            if not generated["generated_dma_csr_enabled"]:
                raise ValueError(f"{mode}: production selected legacy DMA CSR")
            base_sha = generated["csr_base_header_sha256"]
            if not isinstance(base_sha, str) or len(base_sha) != 64:
                raise ValueError(f"{mode}: source-selected CSR base header missing")
            records.append({
                "mode": mode,
                "real_rv32i_linked": True,
                "generated_versus_legacy_image_equal": True,
                "firmware_abi_comparison": "binary_exact",
                "hook": hex(generated["hook"]),
                "binary_sha256": generated["sha256"],
                "legacy_binary_bytes": len(old_bin),
                "generated_binary_bytes": len(new_bin),
                "legacy_elf_bytes": old_elf.stat().st_size,
                "generated_elf_bytes": new_elf.stat().st_size,
                "flash_limit_bytes": generated["flash_limit"],
                "csr_base_header_sha256": base_sha,
                "dma_csr_header_sha256": generated["generated_dma_csr_header_sha256"],
                "protocol_acceptance_proven": False,
                "passive_axi_checked": False,
            })
    if {item["mode"] for item in records} != {name for name, _ in MODES}:
        raise ValueError("missing firmware variant footprint evidence")
    return {
        "schema_version": 1,
        "source_config": config.relative_to(ROOT).as_posix(),
        "source_config_sha256": hashlib.sha256(config_bytes).hexdigest(),
        "kind": "real_rv32i_compile_and_binary_abi_only",
        "cases": records,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=ROOT / "config/soc.yaml")
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    evidence = audit(args.config)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(evidence, indent=2, sort_keys=True) + "\n")
    print(f"PASS {len(evidence['cases'])} real RV32I variant linked-image CSR ABI audits")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
