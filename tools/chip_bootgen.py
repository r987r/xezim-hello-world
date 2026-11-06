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


def build(cfg, *, cpu0_run_hook=None, pcie_host_phase=False):
    addresses = rv.build(cfg, allow_extended_flash_slot=pcie_host_phase)['addresses']  # preserve explicit boot-policy validation
    if cpu0_run_hook is not None:
        flash = next((r for r in cfg['address_map']['data']
                      if r['name'] == 'boot.flash'), None)
        if flash is None or type(cpu0_run_hook) is not int:
            raise ValueError('CPU C run hook must be a configured flash address')
        flash_base = int(flash['base'], 0)
        flash_size = int(flash['size'], 0)
        if cpu0_run_hook % 4 or not flash_base + 0x1000 <= cpu0_run_hook < flash_base + flash_size or cpu0_run_hook > 0xffffffff:
            raise ValueError('CPU C run hook outside reserved aligned flash C region')
    # The host phase protocol is opt-in and never alters regular cold boot.
    peripheral = [s for s in cfg['subsystems']
                  if s['type'] == 'peripheral' and s.get('ip') == 'verilog_pcie']
    if pcie_host_phase and len(peripheral) != 1:
        raise ValueError('host phase requires exactly one configured PCIe peripheral')
    host_base = None
    if pcie_host_phase:
        region = next((r for r in cfg['address_map']['data']
                       if r['name'] == peripheral[0]['name'] + '.sram'), None)
        if region is None:
            raise ValueError('host phase missing configured PCIe SRAM window')
        host_base = int(region['base'], 0) + 0x800
        if int(cfg['boot']['simulation_sram_bytes']) < 0x818:
            raise ValueError('PCIe SRAM too small for host handshake and test payload')
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
            if pcie_host_phase:
                # CPU0 firmware really accesses remote PCIe0 SRAM via data
                # NoCs. Host polls the same bytes via the real TLP/AXI bridge.
                p.li(12, host_base)
                p.store(0xc0011001, 0, base=12)  # DEVICE_INIT_READY
                p.wait(4, 0xc0011002, 'wait_host_init', base=12)
                p.li(5, mailbox)
            p.store(2, 0)
        p.label('run')
        p.store(0x550+index, 8 + 16*index)
        if index == 0:
            p.wait_all(8, 0x550, len(cores), 'wait_hello', increment=True)
            if cpu0_run_hook is not None:
                # CPU0 jumps to real compiled RV32I firmware in the mapped
                # read-only flash, then resumes the existing phase protocol.
                # Stack occupies boot_scratch below the descriptor pool,
                # without touching executing code, mailboxes or DMA data.
                stack = primary_layout.descriptors.start - 16
                if stack & 15:
                    raise ValueError('CPU0 C stack must be 16-byte aligned')
                p.li(2, stack)   # RV32I ABI stack pointer x2
                p.li(10, cpu0_run_hook)  # a0 = C function address
                p.add(rv._jalr(1, 10), 'jalr ra, 0(a0)  # call C DMA run hook')
                p.code.append(((10, 0, 'dma_error'), 'bne a0, zero, dma_error'))
                p.li(5, mailbox)  # C may clobber caller-saved registers
            if pcie_host_phase:
                p.li(12, host_base)
                p.store(0xc0012001, 8, base=12)  # RUN_ENABLE
                p.wait(12, 0xc0012002, 'wait_host_run', base=12)
                p.li(5, mailbox)
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
            if pcie_host_phase:
                p.li(12, host_base)
                p.store(0xc0013001, 16, base=12)  # CHECK_ENABLE
                p.wait(20, 0xc0013002, 'wait_host_check', base=12)
                p.li(5, mailbox)
            p.store(0x600d, done_offset)
        p.add(rv._jal_zero(), 'jal zero, 0  # park')
        if index == 0 and cpu0_run_hook is not None:
            p.label('dma_error')
            p.add(rv._jal_zero(), 'jal zero, 0  # failed C hook: no CHECK')
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
            'sram_bases': [data[c['name']+'.sram'] for c in cores],
            **({'pcie_host_mailbox': host_base} if pcie_host_phase else {})}


def emit(cfg, out: Path, *, cpu0_run_hook=None, pcie_host_phase=False):
    fw = build(cfg, cpu0_run_hook=cpu0_run_hook, pcie_host_phase=pcie_host_phase)
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
    if cpu0_run_hook is not None:
        manifest['cpu0_run_hook'] = cpu0_run_hook
    if pcie_host_phase:
        manifest['external_host'] = {
            'type': 'pcie_root_complex_model', 'coordinator': cfg['boot']['primary'],
            'mailbox_base': fw['pcie_host_mailbox'],
            'roles': ['enumerate', 'init_ack', 'run_data', 'check_ack'],
            'magic': {'device_init_ready': 0xc0011001, 'host_init_ack': 0xc0011002,
                      'run_enable': 0xc0012001, 'host_run_ack': 0xc0012002,
                      'check_enable': 0xc0013001, 'host_check_ack': 0xc0013002},
            'transport': 'real_cpu_axi_to_global_noc_to_pcie0_sram_and_host_tlp_bridge',
        }
    (out/'firmware.json').write_text(json.dumps(manifest, indent=2, sort_keys=True)+'\n')
    return fw, manifest
