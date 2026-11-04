"""Physical SRAM ownership policy shared by the real cold-boot generator and DMA DV.

All offsets below are relative to each compute subsystem's physical SRAM base.
The architectural SRAM window is often larger than the simulated backing SRAM.
This module never deposits data or changes cold-boot behavior.
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
    start: int
    size: int
    lifetime: str

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
    firmware: Region | None
    mailbox: Region | None
    boot_scratch: Region | None
    profile: str
    descriptors: Region
    payload: Region

    def as_dict(self) -> dict:
        return {
            'subsystem': self.subsystem,
            'profile': self.profile,
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


def build_sram_layout(cfg: dict, subsystem: str, *, profile: str = 'boot_live') -> Layout:
    if profile not in ('boot_live', 'dma_only'):
        raise ValueError(f'unknown SRAM profile: {profile}')
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
    mailbox_capacity = 16*ncores + 64
    mailbox_end = mailbox_offset + mailbox_capacity
    if mailbox_end > DESC_START:
        raise ValueError('SRAM mailbox overlaps descriptor pool')
    if profile == 'boot_live':
        fw = Region('firmware', base, stride, 'live')
        mb = Region('mailbox', base+mailbox_offset, mailbox_capacity,
                    'until_check') if subsystem == primary else None
        scratch_start = _align(max(stride, mailbox_end if mb else stride), DESC_ALIGN)
        scratch = Region('boot_scratch', base+scratch_start,
                         DESC_START-scratch_start, 'after_quiescence')
        descriptor_offset, payload_offset = DESC_START, PAYLOAD_START
    else:
        # An isolated DMA-only regression starts from reset with no running CPUs,
        # so it can reuse the entire SRAM including former boot space.
        # Cold boot never uses this profile.
        fw = mb = scratch = None
        descriptor_offset, payload_offset = 0, DESC_BYTES
    descriptors = Region('descriptors', base+descriptor_offset, DESC_BYTES, 'dma')
    payload = Region('payload', base+payload_offset, capacity-payload_offset, 'dma')
    spans = [x for x in (fw, mb, scratch, descriptors, payload) if x is not None]
    for i, first in enumerate(spans):
        if first.size < 0 or first.start < base or first.end > base+capacity:
            raise ValueError(f'{first.name}: region outside SRAM')
        for second in spans[i+1:]:
            if first.size and second.size and max(first.start, second.start) < min(first.end, second.end):
                raise ValueError(f'SRAM overlap: {first.name} and {second.name}')
    return Layout(subsystem, base, capacity, fw, mb, scratch, profile, descriptors, payload)
