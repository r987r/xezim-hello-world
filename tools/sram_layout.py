"""Single SRAM ownership/lifetime policy for generated cold boot and DMA DV.

No simulator, runtime, or RTL may infer that an architectural 1 MiB window
means the backing simulation SRAM has 1 MiB. All offsets are relative to
config/soc.yaml's per-compute physical SRAM bases.
"""
from __future__ import annotations
from dataclasses import dataclass

DESC_START = 0x1000
DESC_BYTES = 0x1000
PAYLOAD_START = DESC_START + DESC_BYTES
DESC_ALIGN = 32


@dataclass(frozen=True)
class Region:
    name: str
    start: int  # physical address
    size: int
    lifetime: str  # 'live', 'until_check', 'after_quiescence', 'dma'

    @property
    def end(self) -> int:
        return self.start + self.size

    def contains(self, start: int, size: int) -> bool:
        return size >= 0 and self.start <= start and start + size <= self.end


@dataclass(frozen=True)
class Layout:
    subsystem: str
    sram_base: int
    sram_size: int
    firmware: Region
    mailbox: Region | None
    boot_scratch: Region
    descriptors: Region
    payload: Region

    def as_dict(self) -> dict:
        return {
            'subsystem': self.subsystem,
            'sram_base': self.sram_base,
            'sram_size': self.sram_size,
            'regions': {
                name: vars(region) if region else None
                for name, region in (
                    ('firmware', self.firmware), ('mailbox', self.mailbox),
                    ('boot_scratch', self.boot_scratch),
                    ('descriptors', self.descriptors), ('payload', self.payload))},
            'boot_reclaim_rule':
                'boot_scratch only after CHECK completion and all CPU/DMA '
                'users quiesced; never reclaim executing firmware or live mailboxes',
        }


def _number(n):
    return int(n, 0) if isinstance(n, str) else int(n)


def _align(n, alignment):
    return (n + alignment - 1) & -alignment


def build_sram_layout(cfg: dict, subsystem: str) -> Layout:
    computes = [s['name'] for s in cfg['subsystems'] if s['type'] == 'compute']
    if subsystem not in computes:
        raise ValueError(f'{subsystem}: not a configured compute subsystem')
    matching = [r for r in cfg['address_map']['data'] if r['name'] == subsystem+'.sram']
    if len(matching) != 1:
        raise ValueError(f'{subsystem}: missing or duplicate SRAM window')
    base, window = _number(matching[0]['base']), _number(matching[0]['size'])
    capacity = _number(cfg['boot']['simulation_sram_bytes'])
    if capacity > window or capacity <= PAYLOAD_START or capacity % 8 or base % DESC_ALIGN:
        raise ValueError(f'{subsystem}: invalid simulated SRAM window')
    stride = _number(cfg['boot'].get('flash_slot_stride', 256))
    mailbox_offset = _number(cfg['verification']['full_chip_boot']['mailbox_offset'])
    ncores = len(computes)
    primary = cfg['boot'].get('primary', computes[0])
    if stride <= 0 or stride > mailbox_offset or stride > DESC_START:
        raise ValueError('SRAM boot image overlaps mailbox/descriptor allocation')
    if mailbox_offset < 256 or mailbox_offset % 4:
        raise ValueError('SRAM mailbox offset must be word aligned and beyond boot code')
    # Cold boot uses 16 bytes/core and a coordinator DONE word; preserve
    # additional 64-byte headroom accepted by the boot generator.
    mailbox_capacity = 16*ncores + 64
    mailbox_end = mailbox_offset + mailbox_capacity
    if mailbox_end > DESC_START:
        raise ValueError('SRAM mailbox overlaps descriptor pool')
    fw = Region('firmware', base, stride, 'live')
    # Only the coordinator SRAM hosts the shared CPU mailboxes.
    mb = Region('mailbox', base+mailbox_offset, mailbox_capacity, 'until_check') if subsystem == primary else None
    # The transient region is not part of executable code or mailboxes.
    scratch_start = _align(max(stride, mailbox_end if mb else stride), DESC_ALIGN)
    scratch = Region('boot_scratch', base+scratch_start,
                     DESC_START-scratch_start, 'after_quiescence')
    descriptors = Region('descriptors', base+DESC_START, DESC_BYTES, 'dma')
    payload = Region('payload', base+PAYLOAD_START, capacity-PAYLOAD_START, 'dma')
    spans = [fw, scratch, descriptors, payload] + ([mb] if mb else [])
    for i, first in enumerate(spans):
        if first.size < 0 or first.start < base or first.end > base+capacity:
            raise ValueError(f'{first.name}: region outside SRAM')
        for second in spans[i+1:]:
            if first.size and second.size and max(first.start, second.start) < min(first.end, second.end):
                raise ValueError(f'SRAM overlap: {first.name} and {second.name}')
    return Layout(subsystem, base, capacity, fw, mb, scratch, descriptors, payload)
