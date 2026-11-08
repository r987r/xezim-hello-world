"""Compile real RV32I freestanding CPU0 C DMA app into an *opt-in* chip image.

Same config, boot ROM, SRAM/NoC wiring, init/run/check checker, iDMA
instances and passive AXI monitors as normal full-chip verification.
No testbench backdoor preload or duplicate RTL; only the immutable flash
image and C-hook-enabled test configuration differ.

All generated variants live in ignored .tools/regression, never tracked gen/.
"""
from __future__ import annotations
import json
import hashlib
import struct
import sys
from pathlib import Path
import shutil
import subprocess
import yaml
from tools import memory_plan

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
HOOK_OFFSET = 0x1000


def require_tool(name):
    found = shutil.which(name)
    if not found:
        raise ValueError(
            f"CPU DMA firmware requires {name}; install clang + llvm-objcopy")
    return found


def compile_firmware(cfg, directory: Path, *, pcie_host_mode=False, ethernet_cpu_mode=False,
                     scenario_mode=False, use_generated_dma_csr=False):
    directory.mkdir(parents=True, exist_ok=True)
    if scenario_mode:
        if pcie_host_mode or ethernet_cpu_mode:
            raise ValueError('scenario CPU mode cannot alias PCIe/Ethernet variants')
        from dv.common.scenario_dma import materialize
        materialize(cfg, directory)
    mapping = {r["name"]: int(r["base"], 0)
               for r in cfg["address_map"]["data"] + cfg["address_map"]["config"]}
    flash_start = mapping["boot.flash"]
    flash_size = int(next(r["size"] for r in cfg["address_map"]["data"]
                          if r["name"] == "boot.flash"), 0)
    hook = flash_start + HOOK_OFFSET
    if hook >= flash_start + flash_size or hook >= 1 << 32:
        raise ValueError("C firmware out of addressable flash range")
    regions = memory_plan.configured_regions(cfg, profile="boot_live")
    if regions["compute0.sram.payload"].base != mapping["compute0.sram"] + 0x2000:
        raise ValueError("CPU source pool address disagrees with SRAM layout")
    if regions["compute1.sram.payload"].base != mapping["compute1.sram"] + 0x2000:
        raise ValueError("CPU peer pool address disagrees with SRAM layout")
    for kind in ("memory0.ddr0", "memory0.hbm0"):
        if regions[kind].base != mapping[kind] + 0x100:
            raise ValueError("CPU target region disagrees with virtual plan")
    model_bytes = 1 << int(cfg["verification"]["memory"]["model_address_bits"])
    macros = {
        "SOC_CPU0_SRAM": mapping["compute0.sram"],
        "SOC_CPU1_SRAM": mapping["compute1.sram"],
        "SOC_DMA0_CSR": mapping["compute0.dma"],
        "SOC_DDR_BASE": mapping["memory0.ddr0"],
        "SOC_HBM_BASE": mapping["memory0.hbm0"],
        "SOC_MODEL_BYTES": model_bytes,
        "SOC_MAILBOX": memory_plan.build_sram_layout(cfg, "compute0").mailbox.start,
    }
    if pcie_host_mode:
        macros["SOC_PCIE_SRAM"] = mapping["pcie0.sram"]
    if ethernet_cpu_mode:
        if pcie_host_mode:
            raise ValueError('Ethernet CPU MVP is separate from the PCIe host test')
        macros['SOC_ETH_SRAM'] = mapping['ethernet0.sram']
        macros['SOC_ETH_CTRL'] = mapping['ethernet0.ctrl']
    linker = directory / "cpu_dma.ld"
    linker.write_text(
        "ENTRY(cpu_dma_run)\nSECTIONS {\n"
        f"  . = 0x{hook:x};\n"
        "  .text : { KEEP(*(.text.cpu_dma_run)) *(.text*) *(.rodata*) }\n"
        "  . = ALIGN(16);\n"
        "  .data : { *(.sdata*) *(.data*) }\n"
        "  .bss (NOLOAD) : { *(.sbss*) *(.bss*) *(COMMON) }\n"
        "}\n"
    )
    elf = directory / "cpu_dma.elf"
    raw = directory / "cpu_dma.bin"
    if use_generated_dma_csr:
        # Software-only schema, no generated RTL or default firmware mutation.
        from tools.csr_dma_headers import emit as emit_dma_header
        emit_dma_header(directory / "csr")
    args = [require_tool("clang"),
            "--target=riscv32-unknown-elf", "-march=rv32i", "-mabi=ilp32",
            "-Oz", "-ffunction-sections", "-ffreestanding", "-fno-builtin",
            "-fno-stack-protector", "-fno-pic", "-fno-pie",
            "-nostdlib", "-fuse-ld=lld", "-Wl,--no-relax",
            "-Wl,--build-id=none", f"-Wl,-T,{linker}",
            *[f"-D{name}=0x{value:x}ULL" for name, value in macros.items()],
            *(['-DSOC_USE_GENERATED_DMA_CSR=1', '-I', str(directory / 'csr')]
              if use_generated_dma_csr else []),
            str(ROOT / ('sw/dma/tests/scenario_dma_run.c' if scenario_mode
                        else 'sw/ethernet/tests/eth_cpu_run.c' if ethernet_cpu_mode
                        else 'sw/dma/tests/cpu_dma_run.c')),
            *(['-I', str(directory)] if scenario_mode else []),
            str(ROOT / "sw/common/memory_pool.c"),
            str(ROOT / "sw/common/memory_pattern.c"),
            str(ROOT / "sw/common/sram_pool.c"),
            str(ROOT / "sw/dma/dma.c"),
            str(ROOT / "sw/common/rv32i_runtime.c"),
            "-o", str(elf)]
    subprocess.run(args, cwd=ROOT, check=True)
    subprocess.run([require_tool("llvm-objcopy"), "-O", "binary",
                    str(elf), str(raw)], cwd=ROOT, check=True)
    elf_bytes = elf.read_bytes()
    if elf_bytes[:6] != b"\x7fELF\x01\x01":
        raise ValueError("CPU DMA compiler did not emit little-endian ELF32")
    actual_entry = struct.unpack_from("<I", elf_bytes, 24)[0]
    if actual_entry != hook:
        raise ValueError(
            f"CPU DMA entry {actual_entry:#x} disagrees with ROM run hook {hook:#x}")
    blob = raw.read_bytes()
    if not blob or len(blob) > flash_size - HOOK_OFFSET:
        raise ValueError(f"C DMA application too large for flash: {len(blob)} bytes")
    # ELF text instructions are aligned, but trailing byte-sized .rodata
    # need not make the binary length word-aligned. Flash emission below
    # pads the final 64-bit readmemh word without changing ELF contents.
    return dict(hook=hook, data=blob, sha256=hashlib.sha256(blob).hexdigest(), compiler="clang/LLVM RV32I",
                defines=macros, flash_limit=flash_size)


def prepare(cfg, noc_manifest, noc_root, output: Path, *, pcie_host_mode=False,
            ethernet_cpu_mode=False, real_ddr_mode=False, ddr_wb_base=0, ddr_wb_adr_bits=30,
            scenario_mode=False, pcie_outbound_mode=False):
    from tools import full_chip_gen
    if scenario_mode and real_ddr_mode:
        raise ValueError('SCN-2 uses modeled DDR; real LiteDRAM requires separate scenario qualification')
    if pcie_outbound_mode and not pcie_host_mode:
        raise ValueError('PCIe outbound requires the real PCIe host variant')
    if pcie_host_mode:
        from tools.pcie_chip import host_variant_config
        cfg = host_variant_config(cfg)
    fw = compile_firmware(cfg, output, pcie_host_mode=pcie_host_mode,
                          ethernet_cpu_mode=ethernet_cpu_mode,
                          scenario_mode=scenario_mode)
    image_prefix = output.relative_to(ROOT).as_posix()
    # Normal generated gen/chip outputs remain byte-for-byte unchanged.
    manifest = full_chip_gen.emit(cfg, noc_manifest, noc_root, output,
                                  cpu0_run_hook=fw["hook"],
                                  image_prefix=image_prefix, cpu_dma_mode=True,
                                  pcie_host_mode=pcie_host_mode,
                                  pcie_outbound_mode=pcie_outbound_mode,
                                  ethernet_mode=ethernet_cpu_mode,
                                  ethernet_cpu_mode=ethernet_cpu_mode,
                                  real_ddr_mode=real_ddr_mode,
                                  ddr_wb_base=ddr_wb_base, ddr_wb_adr_bits=ddr_wb_adr_bits)
    image = output / "flash.hex"
    additional = [f"@{HOOK_OFFSET // 8:x}"]
    blob = fw["data"]
    for n in range(0, len(blob), 8):
        additional.append(f"{int.from_bytes(blob[n:n+8].ljust(8, bytes([0])), 'little'):016x}")
    with image.open("a") as output_file:
        output_file.write("\n" + "\n".join(additional) + "\n")
    # Hardware-visible C evidence will be checked against the golden
    # plan and actual accepted AXI events, not a preload.
    manifest['cpu_ethernet_firmware' if ethernet_cpu_mode else 'cpu_dma_firmware'] = {
        "entry": fw["hook"], "bytes": len(blob), "sha256": fw["sha256"], "file": image_prefix + "/flash.hex",
        "allocation_plan": {name: r.as_dict() for name, r in
                            memory_plan.configured_regions(cfg, profile="boot_live").items()},
    }
    if scenario_mode:
        from dv.common.scenario_dma import load_contract_from_plan
        contract = load_contract_from_plan(output/'scenario-plan.json')
        manifest['scenario_intent'] = {'scenario_id': contract['scenario_id'],
                                       'plan_sha256': contract['plan_sha256'],
                                       'path': str(output/'scenario-plan.json'),
                                       'execution_state': 'pending_real_rtl'}
    (output/"manifest.json").write_text(json.dumps(manifest, indent=2, sort_keys=True)+"\n")
    return manifest


def main():
    import argparse
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("--out", type=Path, required=True)
    options = cli.parse_args()
    cfg = yaml.safe_load((ROOT/"config/soc.yaml").read_text())
    noc_manifest = json.loads((ROOT/"gen/supernoc/manifest.json").read_text())
    output = (ROOT / options.out).resolve()
    if ROOT not in output.parents or ".tools" not in output.relative_to(ROOT).parts:
        raise ValueError("CPU DMA variant must stay in ignored .tools directory")
    print(json.dumps(prepare(cfg,noc_manifest,
                             ROOT/"gen/noc/floonoc",output), indent=2))


if __name__ == "__main__":
    main()
