"""Small deterministic RV32I boot ROM builder for the two-core cold-boot test.

This is deliberately a *firmware image generator*, not an invented controller.
CPU0 fetches immutable ROM, reads read-only simulated flash, writes both SRAMs
through its bus, releases CPU1 through a real MMIO reset register, and branches
to its SRAM program. The flash transport is model-only (SPI/QSPI to follow).
"""
from __future__ import annotations

import json
from pathlib import Path


def _reg(r: int) -> int:
    if not 0 <= r <= 31:
        raise ValueError(f"bad register x{r}")
    return r


def _i(op: int, f3: int, rd: int, rs1: int, imm: int) -> int:
    if not -(1 << 11) <= imm < (1 << 11):
        raise ValueError(f"12-bit immediate: {imm}")
    return ((imm & 0xfff) << 20) | (_reg(rs1) << 15) | (f3 << 12) | (_reg(rd) << 7) | op


def _sw(rs2: int, rs1: int, imm: int) -> int:
    if not -(1 << 11) <= imm < (1 << 11):
        raise ValueError(f"store offset: {imm}")
    x = imm & 0xfff
    return ((x >> 5) << 25) | (_reg(rs2) << 20) | (_reg(rs1) << 15) | (2 << 12) | ((x & 31) << 7) | 0x23


def _bne(rs1: int, rs2: int, displacement: int) -> int:
    if displacement % 2 or not -(1 << 12) <= displacement < (1 << 12):
        raise ValueError("branch displacement outside 13 bits")
    x = displacement & 0x1fff
    return (((x >> 12) & 1) << 31) | (((x >> 5) & 63) << 25) | (_reg(rs2) << 20) | (_reg(rs1) << 15) | (1 << 12) | (((x >> 1) & 15) << 8) | (((x >> 11) & 1) << 7) | 0x63


def _lui(rd: int, value: int) -> int:
    if value & 0xfff:
        raise ValueError("LUI value not page aligned")
    return (value & 0xfffff000) | (_reg(rd) << 7) | 0x37


def _addi(rd: int, rs1: int, imm: int) -> int:
    return _i(0x13, 0, rd, rs1, imm)


def _lw(rd: int, rs1: int, imm: int = 0) -> int:
    return _i(0x03, 2, rd, rs1, imm)


def _jalr(rd: int, rs1: int, imm: int = 0) -> int:
    return _i(0x67, 0, rd, rs1, imm)


def _jal_zero() -> int:
    return 0x0000006f   # jal x0, 0 (self-loop after writing completion)


def _lui_base(address: int) -> int:
    if address < 0 or address > 0xffffffff or address & 0xfff:
        raise ValueError(f"boot address must be 32-bit and page aligned: {address:#x}")
    return address


def build(cfg: dict) -> dict:
    boot = cfg["boot"]
    supported = {
        "strategy": "rom_copy",
        "image_source": "mapped_flash",
        "secondary_release": "mmio",
        "sram_powerup": "unspecified",
    }
    for field, implemented in supported.items():
        if boot.get(field) != implemented:
            raise ValueError(
                f"boot.{field}={boot.get(field)!r} is not implemented; "
                f"this generator supports only {implemented!r}"
            )
    primary, secondary = boot["primary"], boot["secondary"]
    compute = {s['name']: s for s in cfg['subsystems'] if s['type'] == 'compute'}
    if primary == secondary or primary not in compute or secondary not in compute or compute[primary]['cpu']['ip'] != 'picorv32' or compute[secondary]['cpu']['ip'] != 'serv':
        raise ValueError("boot prototype requires PicoRV32 primary and SERV secondary")
    data = {r['name']: int(r['base'], 0) if isinstance(r['base'], str) else r['base'] for r in cfg['address_map']['data']}
    ctrl = {r['name']: int(r['base'], 0) if isinstance(r['base'], str) else r['base'] for r in cfg['address_map']['config']}
    for expected in ('boot.rom', 'boot.flash', f'{primary}.sram', f'{secondary}.sram'):
        if expected not in data:
            raise ValueError(f"missing boot data address: {expected}")
    if 'boot.reset_ctrl' not in ctrl:
        raise ValueError('missing boot.reset_ctrl MMIO allocation')
    rom_base, flash_base = _lui_base(data['boot.rom']), _lui_base(data['boot.flash'])
    sram0 = _lui_base(data[f'{primary}.sram'])
    sram1 = _lui_base(data[f'{secondary}.sram'])
    resetctrl = _lui_base(ctrl['boot.reset_ctrl'])
    if rom_base != 0:
        raise ValueError('boot ROM is expected at reset PC 0x00000000')
    stride = int(boot['flash_slot_stride'], 0) if isinstance(boot['flash_slot_stride'], str) else boot['flash_slot_stride']
    words = boot['program_words']
    if words != 4 or stride != 256 or boot.get('simulation_sram_bytes') != 16384:
        raise ValueError('current executable boot test supports 4-word images, 256-byte flash slots, 16-KiB explicit model SRAM')
    if (flash_base + stride > 0xffffffff) or (sram1 + 0x100 > 0xffffffff):
        raise ValueError('boot mappings exceed 32-bit CPU address space')
    instructions: list[tuple[int, str]] = []

    def add(word: int, asm: str):
        instructions.append((word, asm))

    # x5=t0 source pointer, x6=t1 destination pointer, x7=t2 words left,
    # x28=t3 temporary. Both images are copied over *real CPU0 stores*.
    for label, src, dst in ((primary, flash_base, sram0), (secondary, flash_base + stride, sram1)):
        add(_lui(5, src & ~0xfff), f'lui t0, 0x{src >> 12:x}  # {label} flash')
        if src & 0xfff:
            add(_addi(5, 5, src & 0xfff), f'addi t0, t0, {src & 0xfff}')
        add(_lui(6, dst), f'lui t1, 0x{dst >> 12:x}  # {label} SRAM')
        add(_addi(7, 0, words), f'addi t2, zero, {words}')
        loop_idx = len(instructions)
        add(_lw(28, 5), 'lw t3, 0(t0)')
        add(_sw(28, 6, 0), 'sw t3, 0(t1)')
        add(_addi(5, 5, 4), 'addi t0, t0, 4')
        add(_addi(6, 6, 4), 'addi t1, t1, 4')
        add(_addi(7, 7, -1), 'addi t2, t2, -1')
        branch_offset = 4 * (loop_idx - len(instructions))
        add(_bne(7, 0, branch_offset), f'bne t2, zero, {branch_offset}  # {label} copy')
    add(_lui(5, resetctrl), f'lui t0, 0x{resetctrl >> 12:x}  # reset control')
    add(_addi(6, 0, 1), 'addi t1, zero, 1  # release CPU1')
    add(_sw(6, 5, 0), 'sw t1, 0(t0)')
    add(_lui(5, sram0), f'lui t0, 0x{sram0 >> 12:x}  # execute loaded image')
    add(_jalr(0, 5), 'jalr zero, 0(t0)')

    if len(instructions) * 4 > 4096:
        raise ValueError('boot ROM larger than 4KiB')
    images = {}
    for label, base, signature in ((primary, sram0, 0x55), (secondary, sram1, 0x66)):
        images[label] = [
            (_lui(5, base), f'lui t0, 0x{base >> 12:x}'),
            (_addi(6, 0, signature), f'addi t1, zero, {signature}'),
            (_sw(6, 5, 0x100), 'sw t1, 0x100(t0)  # completion signature'),
            (_jal_zero(), 'jal zero, 0  # parked'),
        ]
    return {
        'bootrom': instructions,
        'images': images,
        'addresses': {'bootrom': rom_base, 'flash': flash_base, 'sram0': sram0,
                      'sram1': sram1, 'reset_ctrl': resetctrl, 'flash_slot_stride': stride,
                      'signature0': sram0 + 0x100, 'signature1': sram1 + 0x100},
    }


def emit(cfg: dict, destination: Path) -> dict:
    fw = build(cfg)
    destination.mkdir(parents=True, exist_ok=True)
    constants = {name.upper() + '_BASE': value for name, value in fw['addresses'].items()
                 if name in ('bootrom', 'flash', 'sram0', 'sram1', 'reset_ctrl')}
    lines = ['// Generated from config/soc.yaml; do not edit.', 'package boot_config_pkg;']
    lines += [f"    localparam logic [31:0] {name} = 32'h{value:08x};"
              for name, value in constants.items()]
    lines += [f"    localparam integer SRAM_BYTES = {cfg['boot']['simulation_sram_bytes']};",
              f"    localparam integer PROGRAM_WORDS = {cfg['boot']['program_words']};",
              f"    localparam integer FLASH_SLOT_WORDS = {fw['addresses']['flash_slot_stride'] // 4};",
              'endpackage', '']
    (destination/'boot_config_pkg.sv').write_text('\n'.join(lines))
    rom = fw['bootrom']
    (destination/'bootrom.hex').write_text('\n'.join(f'{word:08x}' for word, _ in rom) + '\n')
    (destination/'bootrom.lst').write_text('\n'.join(f'0x{i*4:04x}: {word:08x}  {asm}' for i, (word, asm) in enumerate(rom)) + '\n')
    flash_words = [0] * 128
    flash_lines = []
    for slot, (cpu, image) in enumerate(fw['images'].items()):
        start = slot * 64
        for i, (word, asm) in enumerate(image):
            flash_words[start+i] = word
            flash_lines.append(f'0x{fw["addresses"]["flash"] + (start+i)*4:08x}: {word:08x}  {cpu}: {asm}')
    (destination/'flash.hex').write_text('\n'.join(f'{w:08x}' for w in flash_words) + '\n')
    (destination/'flash.lst').write_text('\n'.join(flash_lines)+'\n')
    manifest = {'schema_version': 1, 'boot_mode': 'primary_cpu_rom_to_sram',
                'physical_flash_transport': 'not integrated; memory-mapped read-only flash model',
                'primary': cfg['boot']['primary'], 'secondary': cfg['boot']['secondary'],
                'program_words': cfg['boot']['program_words'],
                'simulated_sram_bytes': cfg['boot']['simulation_sram_bytes'],
                'addresses': fw['addresses'],
                'cpu0_signature_value': 0x55, 'cpu1_signature_value': 0x66,
                'sram_initialization': 'none: CPU0 copies both images with AXI-Lite stores',
                'release_method': 'CPU0 MMIO write to boot.reset_ctrl'}
    (destination/'manifest.json').write_text(json.dumps(manifest, sort_keys=True, indent=2)+'\n')
    return manifest
