"""RV32I bring-up firmware: CPU0 coordinates init/run/check over real buses.

This is deliberately small platform bootstrap glue, not a port of Snitch's
hardware-specific runtime. No CSRs, AMOs, OS, C library or SRAM preload.
"""
import json
from pathlib import Path
import bootgen as rv
from sram_layout import build_sram_layout


class Program:
    def __init__(self):
        self.code = []
        self.labels = {}

    def label(self, name):
        self.labels[name] = len(self.code)*4

    def add(self, word, asm):
        self.code.append((word, asm))

    def li(self, reg, value):
        upper = (value + 0x800) & 0xfffff000
        low = value - upper
        if low > 0x7fffffff:
            low -= 1 << 32
        if upper:
            self.add(rv._lui(reg, upper), f'lui x{reg}, 0x{upper >> 12:x}')
            if low:
                self.add(rv._addi(reg, reg, low), f'addi x{reg}, x{reg}, {low}')
        else:
            self.add(rv._addi(reg, 0, low), f'addi x{reg}, zero, {low}')

    def store(self, value, offset, base=5):
        self.li(6, value)
        self.add(rv._sw(6, base, offset), f'sw x6, {offset}(x{base})')

    def wait(self, offset, expected, name, base=5):
        self.li(6, expected)
        self.label(name)
        self.add(rv._lw(7, base, offset), f'lw x7, {offset}(x{base})')
        self.code.append(((7, 6, name), f'bne x7, x6, {name}'))

    def wait_all(self, offset, expected, count, name, base=5, stride=16, increment=False):
        self.add(rv._addi(11, base, offset), f'addi x11, x{base}, {offset}')
        self.li(9, count)
        self.li(6, expected)
        self.label(name)
        self.add(rv._lw(7, 11), 'lw x7, 0(x11)')
        self.code.append(((7, 6, name), f'bne x7, x6, {name}'))
        self.add(rv._addi(11, 11, stride), f'addi x11, x11, {stride}')
        if increment:
            self.add(rv._addi(6, 6, 1), 'addi x6, x6, 1')
        self.add(rv._addi(9, 9, -1), 'addi x9, x9, -1')
        self.code.append(((9, 0, name), f'bne x9, zero, {name}'))

    def finish(self):
        result = []
        for index, (word, asm) in enumerate(self.code):
            if isinstance(word, tuple):
                a, b, label = word
                word = rv._bne(a, b, self.labels[label] - index*4)
            result.append((word, asm))
        return result


def build(cfg):
    addresses = rv.build(cfg)['addresses']  # preserve explicit boot-policy validation
    primary = cfg['boot']['primary']
    cores = sorted((s for s in cfg['subsystems'] if s['type'] == 'compute'),
                   key=lambda s: (s['name'] != primary, s['name']))
    if cores[0]['cpu']['ip'] != 'picorv32' or any(c['cpu']['ip'] != 'serv' for c in cores[1:]):
        raise ValueError('full-chip boot currently supports PicoRV32 coordinator and SERV secondaries')
    if not 2 <= len(cores) <= 16:
        raise ValueError('full-chip mailbox/reset bootstrap supports 2..16 cores')
    data = {r['name']: int(r['base'], 0) for r in cfg['address_map']['data']}
    options = cfg['verification']['full_chip_boot']
    if options['phases'] != ['init', 'run', 'check']:
        raise ValueError('full-chip bootstrap requires init/run/check phases')
    if options.get('memory_model') != 'axi_to_mem_tc_sram':
        raise ValueError('full-chip boot requires the declared upstream AXI/SRAM model provider')
    # Shared physical SRAM claims: same layout as DMA host vectors.
    # No writable-SRAM preload is introduced into cold boot.
    layouts = {core['name']: build_sram_layout(cfg, core['name']) for core in cores}
    primary_layout = layouts[primary]
    mailbox = primary_layout.mailbox.start
    offset = mailbox - primary_layout.sram_base
    done_offset = 16*len(cores) + 4
    stride = cfg['boot']['flash_slot_stride']
    images = {}
    for index, core in enumerate(cores):
        p = Program()
        p.li(5, mailbox)
        p.label('init')
        p.store(1, 4 + 16*index)
        if index:
            p.li(8, addresses['reset_ctrl'])
            p.store(1, 4*index, base=8)  # real remote configuration-NoC access
            p.wait(0, 2, 'wait_run')
        else:
            p.wait_all(4, 1, len(cores), 'wait_init')
            p.li(8, addresses['reset_ctrl'])
            p.wait_all(4, 1, len(cores)-1, 'wait_config', base=8, stride=4)
            p.store(2, 0)
        p.label('run')
        p.store(0x550+index, 8 + 16*index)
        if index == 0:
            p.wait_all(8, 0x550, len(cores), 'wait_hello', increment=True)
            p.store(3, 0)
        else:
            p.wait(0, 3, 'wait_check')
        p.label('check')
        # Each CPU actually reads another CPU's greeting before acknowledging.
        peer = (index + 1) % len(cores)
        p.wait(8 + 16*peer, 0x550+peer, 'check_peer')
        p.store(1, 12 + 16*index)
        if index == 0:
            p.wait_all(12, 1, len(cores), 'wait_checked')
            p.store(0x600d, done_offset)
        p.add(rv._jal_zero(), 'jal zero, 0  # park')
        image = p.finish()
        if len(image)*4 > min(stride, offset):
            raise ValueError(f'{core["name"]}: phased firmware exceeds configured flash slot/mailbox offset')
        images[core['name']] = image
    rom = Program()
    for index, core in enumerate(cores):
        rom.li(5, addresses['flash'] + index*stride)
        rom.li(8, data[core['name']+'.sram'])
        rom.li(9, len(images[core['name']]))
        rom.label(f'copy_{index}')
        rom.add(rv._lw(7, 5), 'lw x7, 0(x5)')
        rom.add(rv._sw(7, 8, 0), 'sw x7, 0(x8)')
        rom.add(rv._addi(5, 5, 4), 'addi x5, x5, 4')
        rom.add(rv._addi(8, 8, 4), 'addi x8, x8, 4')
        rom.add(rv._addi(9, 9, -1), 'addi x9, x9, -1')
        rom.code.append(((9, 0, f'copy_{index}'), f'bne x9, zero, copy_{index}'))
    # Clear only coordination data with real CPU0 stores before releasing peers.
    rom.li(5, mailbox)
    for off in [0, done_offset, *[4+16*i+j for i in range(len(cores)) for j in (0, 4, 8)]]:
        rom.add(rv._sw(0, 5, off), f'sw zero, {off}(x5)')
    rom.li(5, addresses['reset_ctrl'])
    rom.store((1 << (len(cores)-1))-1, 0)
    rom.li(5, data[primary+'.sram'])
    rom.add(rv._jalr(0, 5), 'jalr zero, 0(x5)')
    return {'cores': cores, 'images': images, 'rom': rom.finish(), 'mailbox': mailbox,
            'done_offset': done_offset, 'stride': stride, 'addresses': addresses,
            'sram_bases': [data[c['name']+'.sram'] for c in cores]}


def emit(cfg, out: Path):
    fw = build(cfg)
    out.mkdir(parents=True, exist_ok=True)
    def words64(words):
        words = list(words)
        if len(words) % 2:
            words.append(0)
        return [words[i] | words[i+1] << 32 for i in range(0, len(words), 2)]
    def listing(name, code):
        (out/f'{name}.lst').write_text('\n'.join(f'{i*4:04x}: {w:08x}  {asm}' for i, (w, asm) in enumerate(code))+'\n')
    (out/'bootrom.hex').write_text('\n'.join(f'{w:016x}' for w in words64(w for w, _ in fw['rom']))+'\n')
    listing('bootrom', fw['rom'])
    flash = []
    for index, core in enumerate(fw['cores']):
        name = core['name']
        code = fw['images'][name]
        flash += [f'@{index*fw["stride"]//8:x}', *[f'{w:016x}' for w in words64(w for w, _ in code)]]
        (out/f'{name}.hex').write_text('\n'.join(f'{w:08x}' for w, _ in code)+'\n')
        listing(name, code)
    (out/'flash.hex').write_text('\n'.join(flash)+'\n')
    manifest = {'coordinator': cfg['boot']['primary'], 'phases': ['init','run','check'],
                'mailbox': fw['mailbox'], 'done_address': fw['mailbox']+fw['done_offset'],
                'hello_base': 0x550, 'completion': 0x600d, 'cores': [
                    {'id': i, 'name': c['name'], 'ip': c['cpu']['ip'], 'sram_base': fw['sram_bases'][i],
                     'words': [w for w, _ in fw['images'][c['name']]]}
                    for i, c in enumerate(fw['cores'])],
                'sram_initialization': 'none: ROM firmware copies images and clears mailboxes through CPU stores',
                'runtime': 'minimal RV32I mailbox bootstrap; not an unmodified Snitch/PULP runtime port'}
    (out/'firmware.json').write_text(json.dumps(manifest, indent=2, sort_keys=True)+'\n')
    return fw, manifest
