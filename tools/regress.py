#!/usr/bin/env python3
"""Resolve standard Bender filelists and execute config/regression.yaml.

No shell evaluation: commands are argv arrays. Each target retains its resolved
filelist, plan, transcript and result under .tools/regression/<target>/.
"""
from __future__ import annotations

import argparse
import copy
import json
import os
from pathlib import Path
import re
import shlex
import shutil
import signal
import subprocess
import sys
import time

import yaml

ROOT = Path(__file__).resolve().parents[1]
ENGINES = {'xezim', 'xezim-compile', 'verilator-lint', 'cocotb-verilator'}
FIELDS = {'engine', 'sources', 'ip', 'top', 'args', 'pass', 'expect_failure',
          'timeout_s', 'memory_config', 'boot_relocate', 'module', 'test_dir',
          'build', 'reuse_build', 'env', 'seed', 'bender_targets', 'mode', 'report', 'firmware_mode', 'opt_in', 'flow_plan', 'logical_test'}


def expand(config, names, stack=()):
    result = []
    for name in names:
        if name in stack:
            raise ValueError(f'cyclic suite: {stack + (name,)}')
        if name in config['tests']:
            result.append(name)
        elif name in config['suites']:
            result.extend(expand(config, config['suites'][name], stack + (name,)))
        else:
            raise ValueError(f'unknown test/suite: {name}')
    return list(dict.fromkeys(result))


def load_config(path):
    # Direct `python tools/regress.py` starts with tools/ on sys.path; the
    # shared DV evidence ABI lives under repository root, not tools/.
    if str(ROOT) not in sys.path:
        sys.path.insert(0, str(ROOT))
    config = yaml.safe_load(path.read_text())
    if set(config) != {'schema_version', 'defaults', 'upstream_noc', 'tests', 'suites'} or config['schema_version'] != 1:
        raise ValueError('unsupported regression schema')
    if set(config['tests']) & set(config['suites']):
        raise ValueError('test and suite names must be distinct')
    for name, test in config['tests'].items():
        if not re.fullmatch(r'[a-z][a-z0-9-]*', name):
            raise ValueError(f'invalid target name: {name}')
        if set(test) - FIELDS or test.get('engine') not in ENGINES:
            raise ValueError(f'{name}: unknown fields or engine')
        if not isinstance(test.get('sources'), str) or not re.fullmatch(r'[a-z][a-z0-9_-]*', test['sources']):
            raise ValueError(f'{name}: invalid Bender source target')
        if not isinstance(test.get('timeout_s', config['defaults']['timeout_s']), int) or test.get('timeout_s', config['defaults']['timeout_s']) <= 0:
            raise ValueError(f'{name}: timeout_s must be positive')
        if not isinstance(test.get('args', []), list) or any(not isinstance(a, str) for a in test.get('args', [])):
            raise ValueError(f'{name}: args must be a string list')
        if test['engine'] in {'xezim', 'cocotb-verilator'} and not test.get('pass'):
            raise ValueError(f'{name}: simulations require an explicit pass marker')
        if test.get('reuse_build') and test['engine'] != 'cocotb-verilator':
            raise ValueError(f'{name}: build reuse is only supported by cocotb-verilator')
        if test.get('mode', 'simulate') not in ('simulate', 'compile') or (test.get('mode') == 'compile' and test['engine'] != 'xezim'):
            raise ValueError(f'{name}: mode=compile requires the Xezim engine')
        if 'opt_in' in test and type(test['opt_in']) is not bool:
            raise ValueError(f'{name}: opt_in must be boolean')
        if test.get('firmware_mode') not in (None, 'cpu_dma', 'pcie_host', 'pcie_dma_host', 'pcie_outbound', 'ethernet_mvp', 'ethernet_cpu', 'ddr_cpu_dma', 'cpu_dma_scenario', 'scenario_bfm', 'peakrdl_reset', 'ethernet_ddr_pcie'):
            raise ValueError(f'{name}: unknown compiled CPU firmware mode')
        if 'flow_plan' in test:
            source=test['flow_plan']
            if (not isinstance(source,str)
                    or not re.fullmatch(r'config/scenarios/[A-Za-z0-9_-]+\.json',source)
                    or not (ROOT/source).is_file()
                    # Only this exact pinned scenario is supported by the
                    # current eight-action C/BFM executor. A new scenario
                    # must add a real adapter rather than silently driving
                    # a different plan than the Test Runs viewer displays.
                    or source != 'config/scenarios/cpu-bfm-ddr-roundtrip.json'
                    or test.get('firmware_mode') not in ('cpu_dma_scenario','scenario_bfm')):
                raise ValueError(f'{name}: unsupported or unsafe executable scenario path')
        if test.get('firmware_mode') in ('cpu_dma_scenario','scenario_bfm') and 'flow_plan' not in test:
            raise ValueError(f'{name}: scenario adapter requires explicit flow_plan')
        if test.get('firmware_mode') == 'peakrdl_reset' and (
                test['engine'] != 'cocotb-verilator'
                or test.get('top') != 'full_chip_tb'
                or 'chip_boot' not in test.get('bender_targets', [])):
            raise ValueError(f'{name}: PeakRDL reset requires real full-chip boot RTL')
        if 'firmware_mode' in test and (
            test['engine'] != 'cocotb-verilator' or
            'chip_boot' not in test.get('bender_targets', []) or
            (test['firmware_mode'] in ('cpu_dma','pcie_dma_host','pcie_outbound','ethernet_mvp','ethernet_cpu','ddr_cpu_dma','cpu_dma_scenario','scenario_bfm','ethernet_ddr_pcie')
             and 'dma' not in test.get('bender_targets', []))):
            raise ValueError(f'{name}: selected test needs real chip RTL and specified active IP')
        if 'report' in test:
            report = test['report']
            required = {'scope','clock','reset','catalog'}
            if (test['engine'] != 'cocotb-verilator' or not isinstance(report, dict)
                or not ({'axi','protocols'} & set(report))
                or set(report) - {'axi','protocols','memory','context','flow','address_map','fabric_scope','fabric_benchmark'}
                or ('context' in report and not isinstance(report['context'],str))):
                raise ValueError(f'{name}: invalid protocol report configuration for cocotb-verilator')
            if 'fabric_scope' in report and report['fabric_scope'] not in (
                    'isolated_local_noc', 'connected_noc', 'full_chip_boot_bfm'):
                raise ValueError(f'{name}: unknown physical fabric evidence scope')
            if 'fabric_benchmark' in report:
                benchmark = report['fabric_benchmark']
                if (not isinstance(benchmark,dict)
                        or set(benchmark) != {'profile','spec'}
                        or benchmark['profile'] != 'unloaded'
                        or benchmark['spec'] != 'config/fabric_latency.yaml'
                        or report.get('fabric_scope') not in
                            ('isolated_local_noc','connected_noc','full_chip_boot_bfm')
                        or test.get('module') not in
                            ('test_latency', 'dv.full_chip.test_latency')):
                    raise ValueError(f'{name}: source-selected fabric benchmark contract invalid')
            if 'address_map' in report:
                amap = report['address_map']
                if (not isinstance(amap, dict) or not {'config','variant'} <= set(amap)
                        or set(amap)-{'config','variant','csr_map'}
                        or any(not isinstance(amap[k],str) or not amap[k]
                               for k in amap)):
                    raise ValueError(f'{name}: invalid variant-bound address map report configuration')
            if 'flow' in report:
                flow = report['flow']
                if not isinstance(flow, dict) or not {'required_steps'} <= set(flow) or set(flow)-{'required_steps','firmware_mmio','required_origins'}:
                    raise ValueError(f'{name}: invalid test-flow configuration')
                flow_required = flow['required_steps']
                if (not isinstance(flow_required, dict) or set(flow_required) != {'init','run','check'} or
                        any(not isinstance(items, list) or not items or len(set(items)) != len(items) or
                            any(not isinstance(s, str) or not re.fullmatch(r'[a-z][a-z0-9_.-]*\.[a-z][a-z0-9_.-]*', s)
                                for s in items) for items in flow_required.values())):
                    raise ValueError(f'{name}: invalid required test-flow steps')
                if 'required_origins' in flow:
                    from dv.common.test_flow import ORIGINS
                    origins=flow['required_origins']
                    if (not isinstance(origins,dict) or set(origins)-set(flow_required)
                            or any(not isinstance(mapping,dict) or
                                   any(item not in flow_required[phase] or origin not in ORIGINS
                                       for item,origin in mapping.items())
                                   for phase,mapping in origins.items())):
                        raise ValueError(f'{name}: invalid required step provenance')
                if 'firmware_mmio' in flow:
                    fw = flow['firmware_mmio']
                    if (not isinstance(fw,dict) or set(fw) != {'monitor','address','actors','steps'}
                            or not isinstance(fw['monitor'],str)
                            or not isinstance(fw['address'],str)
                            or not isinstance(fw['actors'],dict)
                            or not isinstance(fw['steps'],dict)):
                        raise ValueError(f'{name}: invalid firmware test-flow adapter')
                    try:
                        int(fw['address'],0)
                        assert fw['actors'] and fw['steps']
                        for table in (fw['actors'],fw['steps']):
                            for num,label in table.items():
                                assert str(int(num))==num
                                assert isinstance(label,str) and re.fullmatch(r'[a-z][a-z0-9_.-]*',label)
                    except (ValueError,AssertionError,TypeError) as exc:
                        raise ValueError(f'{name}: invalid firmware codebook') from exc
            if 'memory' in report:
                m = report['memory']
                if ('axi' not in report or not isinstance(m,dict) or
                    set(m) != {'required','policies'} or m['required'] is not True or
                    m['policies'] != ['strict','fast','hybrid']):
                    raise ValueError(f'{name}: memory report requires AXI and strict/fast/hybrid')
            if 'axi' in report:
                axi = report['axi']
                if (not isinstance(axi, dict)
                    or not required <= set(axi)
                    or set(axi) - required - {'max_events','actors','required_complete'}
                    or ('actors' in axi and not isinstance(axi['actors'],str))
                    or ('required_complete' in axi and type(axi['required_complete']) is not bool)
                    or any(not isinstance(axi[k],str) or not axi[k] for k in required)
                    or type(axi.get('max_events',500000)) is not int
                    or axi.get('max_events',500000) <= 0):
                    raise ValueError(f'{name}: invalid AXI report configuration for cocotb-verilator')
            if 'protocols' in report:
                from protocol_report import normalize_sources
                p = report['protocols']
                if (not isinstance(p,dict) or set(p)-{'sources','max_events'}
                    or type(p.get('max_events',100000)) is not int
                    or p.get('max_events',100000) <= 0):
                    raise ValueError(f'{name}: invalid generic protocol report configuration')
                try:
                    normalize_sources(p.get('sources'))
                except ValueError as exc:
                    raise ValueError(f'{name}: invalid generic protocol report configuration: {exc}') from exc
    for name in config['suites']:
        expand(config, [name])
    opt_in = {name for name, test in config['tests'].items() if test.get('opt_in') is True}
    required = set(config['tests']) - opt_in
    if set(expand(config, ['full'])) != required:
        raise ValueError('full suite must cover every non-opt-in declared test')
    if any(not any(name in expand(config, [suite]) for suite in config['suites'] if suite != 'full') for name in opt_in):
        raise ValueError('opt-in regression must remain addressable through a named suite')
    from test_identity import catalog as validate_identity_catalog
    validate_identity_catalog(config["tests"])
    from runtime_contract import validate_migration_inventory
    validate_migration_inventory(config)
    return config


def executable(env_name, cached, fallback):
    value = os.environ.get(env_name) or (str(cached) if cached.is_file() else shutil.which(fallback))
    if not value or not Path(value).is_file() or not os.access(value, os.X_OK):
        raise ValueError(f'missing {fallback}: set {env_name} or install {cached}')
    return str(Path(value).resolve())


def capture(command, cwd=ROOT):
    result = subprocess.run(command, cwd=cwd, capture_output=True, text=True, timeout=180)
    if result.returncode:
        raise ValueError(f'{shlex.join(command)} failed: {result.stderr[-4000:]}')
    return result.stdout


def parse_filelist(text):
    """Bender flist-plus: ordered sources, +incdir+ and +define+ only."""
    sources, includes, defines = [], [], []
    for line in text.splitlines():
        if not line.strip() or line.lstrip().startswith('//'):
            continue
        for token in shlex.split(line):
            if token.startswith('+incdir+'):
                includes.extend(token[len('+incdir+'):].split('+'))
            elif token.startswith('+define+'):
                defines.extend(token[len('+define+'):].split('+'))
            elif token.startswith(('+', '-')):
                raise ValueError(f'unsupported Bender filelist token: {token}')
            else:
                sources.append(str((ROOT / token).resolve()))
    if not sources:
        raise ValueError('empty Bender source set')
    for filename in sources:
        if not Path(filename).is_file():
            raise ValueError(f'missing RTL: {filename}')
    return sources, list(dict.fromkeys(includes)), list(dict.fromkeys(defines))


def noc_contracts():
    import floonoc_gen
    cfg = yaml.safe_load((ROOT/'config/soc.yaml').read_text())
    knobs = yaml.safe_load((ROOT/'config/interface_contracts.yaml').read_text())
    root = ROOT/'gen/noc/floonoc'
    networks = json.loads((root/'manifest.json').read_text())['networks']
    expected = floonoc_gen.profiles(cfg, knobs)
    if set(networks) != set(expected) or not networks:
        raise ValueError('NoC manifest does not match configured network names')
    for name, entry in networks.items():
        top = (root/entry['top']).read_text()
        pkg = (root/entry['package']).read_text()
        profile = yaml.safe_load((root/entry['config']).read_text())
        count = entry['network_interfaces_with_native_knobs']
        dest = sum(bool(e.get('sbr_port_protocol')) for e in profile['endpoints'])
        src = sum(bool(e.get('mgr_port_protocol')) for e in profile['endpoints'])
        checks = [src + dest == count, 'floo_axi_router' in top, 'floo_axi_chimney' in top,
                  'package ' in pkg, top.count(".AtopSupport(1'b0)") == count,
                  top.count('.MaxAtomicTxns(0)') == count,
                  top.count('set_ports(xezim_chimney_cfg_no_mgr(),') == dest,
                  top.count('set_ports(xezim_chimney_cfg(),') == src]
        if not all(checks):
            raise ValueError(f'{name}: generated router/chimney/native role contract failed')
    return networks


class Resolver:
    def __init__(self, config):
        self.config = config
        self.cache = {}
        self.fetched = set()
        self.bender = executable('BENDER_BIN', ROOT/'.tools/bin/bender', 'bender')

    def sources(self, test):
        import ip_fetch
        for ip in test.get('ip', []) + (['floonoc'] if test['sources'] == 'noc' else []):
            if ip not in self.fetched:
                ip_fetch.fetch(ip)
                self.fetched.add(ip)
        target = test['sources']
        if target not in self.cache:
            if target == 'noc':
                vendor = ROOT/'.tools/floonoc'
                lock = (vendor/'Bender.lock').read_bytes()
                capture([self.bender, '-d', str(vendor), 'checkout'])
                text = capture([self.bender, '-d', str(vendor), 'script', 'flist-plus',
                                *[x for t in self.config['upstream_noc']['targets'] for x in ('-t', t)]])
                if (vendor/'Bender.lock').read_bytes() != lock:
                    raise ValueError('Bender modified the pinned upstream lock')
                patterns = self.config['upstream_noc']['exclude_paths']
                text = '\n'.join(line for line in text.splitlines()
                                 if not any(re.search(p, line) for p in patterns))
            else:
                text = capture([self.bender, 'script', 'flist-plus', '-t', target])
            self.cache[target] = parse_filelist(text)
        return copy.deepcopy(self.cache[target])


def boot_variant(overrides, out):
    import bootgen
    import socgen
    cfg = yaml.safe_load((ROOT/'config/soc.yaml').read_text())
    remaining = set(overrides)
    for region in cfg['address_map']['data'] + cfg['address_map']['config']:
        if region['name'] in overrides:
            region['base'] = overrides[region['name']]
            remaining.remove(region['name'])
    if remaining:
        raise ValueError(f'unknown boot mapping overrides: {sorted(remaining)}')
    socgen.validate(cfg)
    bootgen.emit(cfg, out)
    (out/'soc.yaml').write_text(yaml.safe_dump(cfg, sort_keys=False))


def filelist_text(sources, includes, defines):
    return '\n'.join(shlex.quote(t) for t in [*['+incdir+' + p for p in includes],
                                             *['+define+' + d for d in defines], *sources]) + '\n'


def check_outcome(code, text, test, timed_out=False):
    if timed_out:
        return False, 'wall-clock timeout'
    if test.get('expect_failure'):
        ok = code > 0 and test['expect_failure'] in text and test['pass'] not in text
        return ok, 'expected named failure detected' if ok else 'negative result missing/wrong/unexpectedly passed'
    ok = code == 0 and (not test.get('pass') or test['pass'] in text)
    return ok, 'completed' if ok else 'nonzero exit or missing pass marker'


def run_process(command, log, timeout, env):
    with log.open('w') as stream:
        stream.write(shlex.join(command) + '\n')
        stream.flush()
        process = subprocess.Popen(command, cwd=ROOT, env=env, stdout=stream,
                                   stderr=subprocess.STDOUT, start_new_session=True)
        try:
            return process.wait(timeout=timeout), False
        except subprocess.TimeoutExpired:
            os.killpg(process.pid, signal.SIGKILL)
            process.wait()
            return process.returncode, True


def run_target(name, test, resolver, options):
    out = ROOT/'.tools/regression'/name
    if out.exists():
        shutil.rmtree(out)
    out.mkdir(parents=True, exist_ok=True)
    # Each attempt replaces prior logs/filelists/results. The separately
    # fingerprinted Verilator build directory survives for explicit reuse.
    sources, includes, defines = resolver.sources(test)
    args = list(test.get('args', [])) + options.arg
    if test.get('memory_config') or options.memory_config:
        import socgen
        config = ROOT/(options.memory_config or test['memory_config'])
        capture([sys.executable, str(ROOT/'tools/socgen.py'), '--config', str(config), '--out', str(out/'memory')])
        sources = [str(out/'memory/memory_tb.sv') if p == str(ROOT/'gen/memory/memory_tb.sv') else p for p in sources]
    if test.get('boot_relocate'):
        boot_variant(test['boot_relocate'], out/'boot')
        sources = [str(out/'boot/boot_config_pkg.sv') if p == str(ROOT/'gen/boot/boot_config_pkg.sv') else p for p in sources]
        args += [f'+BOOTROM_FILE={out}/boot/bootrom.hex', f'+FLASH_FILE={out}/boot/flash.hex']
    networks = noc_contracts() if test['sources'] == 'noc' else {}
    root = ROOT/'gen/noc/floonoc'
    if options.network and (test['engine'] not in {'xezim-compile', 'verilator-lint'} or set(options.network) - set(networks)):
        raise ValueError('--network requires known structural NoC network names')
    for network, entry in sorted(networks.items()):
        (out/f'{network}.f').write_text(filelist_text(
            sources + [str(root/entry['package']), str(root/entry['top'])], includes, defines))
    if networks and test['engine'] not in {'xezim-compile', 'verilator-lint'}:
        sources += [str(root/entry['package']) for _, entry in sorted(networks.items())]
        sources += [str(root/entry['top']) for _, entry in sorted(networks.items())]
    if 'dma' in test.get('bender_targets', []):
        import idma_rtl
        # Pinned source is already fetched; generate backend + PeakRDL RTL
        # before Bender expands the dma source set. This shares the existing
        # FlooNoC AXI dependency graph; no second AXI checkout is introduced.
        idma_rtl.generate()
        # FlooNoC's Bender.lock also pins PULP APB, but our standard NoC
        # source exclusion removes its unused files and include directories.
        # Bring back ONLY the genuine upstream APB pkg/typedef for desc64.
        # Never fetch a second APB/AXI revision or copy these definitions.
        apb_root = Path(capture([resolver.bender, '-d',
                                 str(ROOT/'.tools/floonoc'), 'path', 'apb']).strip())
        if not (apb_root/'src/apb_pkg.sv').is_file():
            raise ValueError('pinned FlooNoC APB package missing')
        sources.insert(0, str(apb_root/'src/apb_pkg.sv'))
        includes += [str(apb_root/'include'),
                     str(ROOT/'.tools/pulp_idma/src/include'),
                     str(ROOT/'.tools/pulp_idma/target/rtl/include')]
    for target in test.get('bender_targets', []):
        extra, inc, defs = resolver.sources({'sources': target})
        sources += extra
        includes += inc
        defines += defs
    if test.get('firmware_mode') in ('cpu_dma', 'cpu_dma_scenario'):
        # Compile real C firmware into an alternate immutable FLASH image;
        # change only this run's generated top/checker, not tracked gen/.
        # Script invocation from tools/ otherwise omits the repository root
        # from sys.path; the shared tools.memory_plan namespace needs it.
        if str(ROOT) not in sys.path:
            sys.path.insert(0, str(ROOT))
        from cpu_dma_firmware import prepare as prepare_cpu_dma
        cfg = yaml.safe_load((ROOT/'config/soc.yaml').read_text())
        noc_manifest = json.loads((ROOT/'gen/supernoc/manifest.json').read_text())
        variant = out/'variant'
        prepare_cpu_dma(cfg, noc_manifest, ROOT/'gen/noc/floonoc', variant,
                        scenario_mode=test['firmware_mode']=='cpu_dma_scenario')
        generated_root = ROOT/'gen/chip'
        replacements = {'soc_top.sv', 'full_chip_tb.sv', 'full_chip_dma_tb.sv'}
        sources = [str(variant/Path(filename).name)
                   if Path(filename).parent == generated_root and
                   Path(filename).name in replacements else filename
                   for filename in sources]
    if test.get('firmware_mode') in ('ethernet_mvp', 'ethernet_cpu'):
        if str(ROOT) not in sys.path:
            sys.path.insert(0,str(ROOT))
        from full_chip_gen import emit as emit_chip
        from dv.ethernet0.run_mac_gmii import fetch_pinned
        cfg = yaml.safe_load((ROOT/'config/soc.yaml').read_text())
        noc_manifest = json.loads((ROOT/'gen/supernoc/manifest.json').read_text())
        variant = out/'variant'
        if test['firmware_mode'] == 'ethernet_cpu':
            from cpu_dma_firmware import prepare as prepare_cpu_firmware
            prepare_cpu_firmware(cfg,noc_manifest,ROOT/'gen/noc/floonoc',variant,
                                 ethernet_cpu_mode=True)
        else:
            emit_chip(cfg,noc_manifest,ROOT/'gen/noc/floonoc',variant,
                      image_prefix=variant.relative_to(ROOT).as_posix(),
                      ethernet_mode=True)
        generated_root=ROOT/'gen/chip'
        replacements={'soc_top.sv','full_chip_tb.sv','full_chip_dma_tb.sv'}
        sources=[str(variant/Path(filename).name)
                 if Path(filename).parent==generated_root and
                 Path(filename).name in replacements else filename
                 for filename in sources]
        eth_rtl=ROOT/'rtl/io/ethernet0'
        sources += [str(eth_rtl/name) for name in (
            'ethernet0_axi_mvp.sv','ethernet0_mvp.v','ethernet0_rx_mvp.v',
            'ethernet0_tx_mvp.v','ethernet0_rx_gmii_stager.v',
            'ethernet0_mac_gmii.v','ethernet_rx_frame_stager.v',
            'ethernet_rx_queue_engine.v','ethernet_queue_ctrl.sv',
            'ethernet_rx_desc_fetch.v','ethernet_rx_dma.v',
            'ethernet_tx_dma.v','ethernet_cq_axi_writer.v',
            'ethernet_queue_axi_regs.sv')]
        for directory,meta in fetch_pinned().values():
            sources += [str(directory/name) for name in meta['modules']]
        sources += [str(ROOT/'.tools/verilog_axi/rtl'/name)
                    for name in ('axi_dma_rd.v','axi_dma_wr.v')]
    if test.get('firmware_mode') in ('pcie_host', 'pcie_dma_host', 'pcie_outbound'):
        if str(ROOT) not in sys.path:
            sys.path.insert(0, str(ROOT))
        # Same generated SoC and CPU firmware semantics; only variant wires
        # the real pinned PCIe bridge and CPU0<->host SRAM phase barriers.
        from full_chip_gen import emit as emit_chip
        from dv.pcie0.run_rtl_smoke import source_contract
        from dv.pcie0.prepare_rtl import assert_iverilog_clean
        cfg = yaml.safe_load((ROOT/'config/soc.yaml').read_text())
        noc_manifest = json.loads((ROOT/'gen/supernoc/manifest.json').read_text())
        variant = out/'variant'
        vendor_pin = source_contract()
        bridge = assert_iverilog_clean()
        if test['firmware_mode'] in ('pcie_dma_host', 'pcie_outbound'):
            from cpu_dma_firmware import prepare as prepare_cpu_dma
            prepare_cpu_dma(cfg, noc_manifest, ROOT/'gen/noc/floonoc', variant,
                            pcie_host_mode=True,
                            pcie_outbound_mode=test['firmware_mode']=='pcie_outbound')
        else:
            emit_chip(cfg, noc_manifest, ROOT/'gen/noc/floonoc', variant,
                      image_prefix=variant.relative_to(ROOT).as_posix(),
                      pcie_host_mode=True)
        generated_root = ROOT/'gen/chip'
        replacements = {'soc_top.sv', 'full_chip_tb.sv'}
        sources = [str(variant/Path(filename).name)
                   if Path(filename).parent == generated_root and
                   Path(filename).name in replacements else filename
                   for filename in sources]
        sources += [str(bridge)] + [
            str(ROOT/'.tools/verilog_pcie'/item)
            for item in vendor_pin['rtl_modules'] if item != 'rtl/pcie_axi_master.v']
        if test['firmware_mode'] == 'pcie_outbound':
            required = ['rtl/dma_if_pcie.v','rtl/dma_if_pcie_rd.v',
                        'rtl/dma_if_pcie_wr.v','rtl/priority_encoder.v',
                        'rtl/pulse_merge.v']
            if vendor_pin.get('outbound_rtl_modules') != required:
                raise ValueError('unreviewed pinned PCIe outbound requester source list')
            sources += [str(ROOT/'.tools/verilog_pcie'/item) for item in required]
            sources += [str(ROOT/'rtl/adapters/pcie_dma_sram_target.sv')]
            sources += [str(ROOT/'rtl/adapters/pcie_requester_axi_regs.sv')]
    if test.get('firmware_mode') == 'ddr_cpu_dma':
        # Same CPU C/iDMA INIT/RUN/CHECK; opt-in generated 16KiB
        # independent Config NoC and pinned LiteDRAM memory target.
        if str(ROOT) not in sys.path:
            sys.path.insert(0, str(ROOT))
        import ddr_chip
        from cpu_dma_firmware import prepare as prepare_cpu_dma
        cfg = yaml.safe_load((ROOT/'config/soc.yaml').read_text())
        info = ddr_chip.prepare(cfg, out)
        variant = out / 'variant'
        prepare_cpu_dma(info['variant_cfg'], info['noc_manifest'], info['noc_root'],
                        variant, real_ddr_mode=True,
                        ddr_wb_base=info['wb_base'], ddr_wb_adr_bits=info['wb_bits'])
        generated_root = ROOT/'gen/chip'
        replacements = {'soc_top.sv', 'full_chip_tb.sv'}
        sources = [str(variant/Path(filename).name)
                   if Path(filename).parent == generated_root
                   and Path(filename).name in replacements else filename
                   for filename in sources]
        sources = ddr_chip.source_closure(sources, info)
    if test.get('firmware_mode') == 'ethernet_ddr_pcie':
        # Compose the three real opt-in source closures in one variant. In
        # particular use the re-generated DDR NoCs, NOT default reserved
        # attachments. No second firmware image or fabricated PHY/host RAM.
        if str(ROOT) not in sys.path:
            sys.path.insert(0, str(ROOT))
        import ddr_chip
        from cpu_dma_firmware import prepare as prepare_cpu_firmware
        from dv.ethernet0.run_mac_gmii import fetch_pinned
        from dv.pcie0.run_rtl_smoke import source_contract
        from dv.pcie0.prepare_rtl import assert_iverilog_clean
        cfg = yaml.safe_load((ROOT/'config/soc.yaml').read_text())
        info = ddr_chip.prepare(cfg, out)
        variant = out / 'variant'
        prepare_cpu_firmware(info['variant_cfg'], info['noc_manifest'],
                             info['noc_root'], variant,
                             pcie_host_mode=True, ethernet_cpu_mode=True,
                             real_ddr_mode=True, combined_mode=True,
                             ddr_wb_base=info['wb_base'],
                             ddr_wb_adr_bits=info['wb_bits'])
        generated_root = ROOT/'gen/chip'
        replacements = {'soc_top.sv', 'full_chip_tb.sv'}
        sources = [str(variant/Path(filename).name)
                   if Path(filename).parent == generated_root
                   and Path(filename).name in replacements else filename
                   for filename in sources]
        sources = ddr_chip.source_closure(sources, info)
        eth_rtl = ROOT/'rtl/io/ethernet0'
        sources += [str(eth_rtl/name) for name in (
            'ethernet0_axi_mvp.sv','ethernet0_mvp.v','ethernet0_rx_mvp.v',
            'ethernet0_tx_mvp.v','ethernet0_rx_gmii_stager.v',
            'ethernet0_mac_gmii.v','ethernet_rx_frame_stager.v',
            'ethernet_rx_queue_engine.v','ethernet_queue_ctrl.sv',
            'ethernet_rx_desc_fetch.v','ethernet_rx_dma.v',
            'ethernet_tx_dma.v','ethernet_cq_axi_writer.v',
            'ethernet_queue_axi_regs.sv')]
        for directory,meta in fetch_pinned().values():
            sources += [str(directory/name) for name in meta['modules']]
        sources += [str(ROOT/'.tools/verilog_axi/rtl'/name)
                    for name in ('axi_dma_rd.v','axi_dma_wr.v')]
        vendor_pin = source_contract()
        bridge = assert_iverilog_clean()
        sources += [str(bridge)] + [
            str(ROOT/'.tools/verilog_pcie'/item)
            for item in vendor_pin['rtl_modules'] if item != 'rtl/pcie_axi_master.v']
    if test.get('firmware_mode') == 'peakrdl_reset':
        # Generate the opt-in reset bank without mutating checked-in gen/chip.
        from full_chip_gen import emit as emit_chip
        from csrgen import generate as generate_csr
        cfg = yaml.safe_load((ROOT/'config/soc.yaml').read_text())
        noc_manifest = json.loads((ROOT/'gen/supernoc/manifest.json').read_text())
        variant = out/'variant'
        variant.mkdir(parents=True, exist_ok=True)
        emit_chip(cfg, noc_manifest, ROOT/'gen/noc/floonoc', variant,
                  image_prefix=variant.relative_to(ROOT).as_posix(),
                  peakrdl_reset=True)
        generated_root = ROOT/'gen/chip'
        replacements = {'soc_top.sv', 'full_chip_tb.sv', 'full_chip_dma_tb.sv'}
        sources = [str(variant/Path(filename).name)
                   if Path(filename).parent == generated_root
                   and Path(filename).name in replacements else filename
                   for filename in sources]
        csr_out = out/'csr'
        generate_csr(ROOT/'config/soc.yaml', ROOT/'csr/rdl/boot_reset_ctrl.rdl',
                     csr_out, 'cold_boot')
        pkg = str(csr_out/'rtl/soc_boot_reset_ctrl_regblock_pkg.sv')
        bank = str(csr_out/'rtl/soc_boot_reset_ctrl_regblock.sv')
        top_src = str(variant/'soc_top.sv')
        if sources.count(top_src) != 1:
            raise ValueError('expected one generated SoC RTL top in PeakRDL variant')
        sources[sources.index(top_src):sources.index(top_src)] = [pkg, bank]
    if test.get('firmware_mode') == 'scenario_bfm':
        from dv.common.scenario_dma import materialize
        cfg = yaml.safe_load((ROOT/'config/soc.yaml').read_text())
        materialize(cfg, out)
    sources = list(dict.fromkeys(sources))
    includes = list(dict.fromkeys(includes))
    defines = list(dict.fromkeys(defines))
    filelist = out/'sources.f'
    filelist.write_text(filelist_text(sources, includes, defines))
    # Capture the single source-selected identity before the RTL executor runs.
    # Keep legacy target artifact paths stable while old CI consumers migrate.
    from test_identity import selected as select_identity, save as save_identity, relative_path
    identity = select_identity(name, {**test, "source_target": test["sources"],
                                     "args": args}, filelist=filelist)
    save_identity(out/'identity.json', identity)
    plan = {**test, 'target': name, 'source_target': test['sources'],
            'sources': sources, 'includes': includes, 'defines': defines,
            'args': args, 'results_xml': str(out/'results.xml'), 'stage': options.stage,
            'identity': identity}
    if test['engine'] in {'xezim-compile', 'verilator-lint'} and networks:
        plan['selected_networks'] = {
            net: {'filelist': str(out/f'{net}.f'), 'top': entry['top_module']}
            for net, entry in sorted(networks.items())
            if not options.network or net in options.network
        }
    plan_file = out/'plan.json'
    plan_file.write_text(json.dumps(plan, indent=2) + '\n')
    # Preserve the ACTUAL selected filelist/RTL after all runtime variant
    # substitutions. No simulator or elaborator has executed at this point.
    from selected_rtl_provenance import archive_selected_filelist
    selected_inputs = archive_selected_filelist(ROOT, name, test, plan, filelist)
    plan["selected_source_manifest"] = {
        "path": str((out/'selected-rtl-manifest.json').relative_to(ROOT)),
        "compiler_input_sha256": selected_inputs["compiler_input_sha256"],
    }
    plan_file.write_text(json.dumps(plan, indent=2) + '\n')
    # A separate source-fingerprinted *command dispatch envelope* is not
    # another INIT/RUN/CHECK scenario planner. The canonical intent remains
    # planned-flow.json and the original scenario-plan.json for SCN-2.
    from runtime_contract import selection as select_runtime, save as save_runtime
    from runtime_contract import dispatch_event, check_events
    selected_path = out/'selected-test-plan.json'
    save_runtime(selected_path, select_runtime(name,plan,out,commands=[]))
    if options.stage == 'files':
        print(f'FILES {name}: {filelist.relative_to(ROOT)}', flush=True)
        return True
    if options.stage == 'run' and test['engine'] != 'cocotb-verilator':
        raise ValueError('run-only requires cocotb-verilator; Xezim compiles and runs in one invocation')
    engine = test['engine']
    commands = []
    if engine in {'xezim-compile', 'verilator-lint'}:
        for network, entry in sorted(networks.items()):
            if options.network and network not in options.network:
                continue
            network_list = str(out/f'{network}.f')
            if engine == 'xezim-compile':
                sim = executable('XEZIM_BIN', ROOT/'.tools/bin/xezim-linux-x86_64', 'xezim')
                commands.append((network, [sim, '--compile', '--no-cache', '-s', entry['top_module'], '-f', network_list, *args]))
            else:
                sim = shutil.which('verilator')
                if not sim:
                    raise ValueError('verilator missing from PATH')
                commands.append((network, [sim, '--lint-only', '--timing', '-Wno-fatal', '--top-module', entry['top_module'], '-f', network_list, *args]))
        if not commands or set(options.network) - set(networks):
            raise ValueError('empty or unknown NoC network selection')
    elif engine == 'xezim':
        sim = executable('XEZIM_BIN', ROOT/'.tools/bin/xezim-linux-x86_64', 'xezim')
        commands = [(name, [sim, *(['--compile'] if options.stage == 'build' or test.get('mode') == 'compile' else []), '--no-cache', '-s', test['top'], '-f', str(filelist), *args])]
    else:
        commands = [(name, [sys.executable, str(ROOT/'tools/sim_cocotb.py'), str(plan_file)])]
    plan['commands'] = commands
    plan_file.write_text(json.dumps(plan, indent=2) + '\n')
    # Resolve and archive the exact declared intent BEFORE the simulator is
    # launched, including the selected command arguments. This is *not* a
    # claim of dispatch, completion or PASS. Incomplete/failed runs retain it.
    from test_intent import snapshot as snapshot_intent, validate_snapshot
    scenario = None
    if test.get('firmware_mode') in ('scenario_bfm', 'cpu_dma_scenario'):
        # Reuse the already resolved immutable plan that the C/BFM adapter
        # consumes. Reading the authoring spec here would lose selected
        # randomized arguments and resolved buffer addresses.
        scenario_location = out/('variant' if test['firmware_mode']=='cpu_dma_scenario' else '')/'scenario-plan.json'
        if not scenario_location.is_file():
            raise ValueError('runtime-resolved scenario plan missing before pre-run snapshot')
        scenario = json.loads(scenario_location.read_text())
    from stimulus_catalog import load as load_stimuli
    # The local `cfg` name is reserved for per-variant SoC configurations;
    # always read the existing top-level regression selection authority.
    regression_catalog = yaml.safe_load((ROOT/'config/regression.yaml').read_text())
    selected = snapshot_intent(name, plan, scenario=scenario,
                               stimulus=load_stimuli(regression_catalog)[name])
    validate_snapshot(selected, target=name)
    (out/'planned-flow.json').write_text(json.dumps(selected, indent=2) + '\n')
    # Before simulator dispatch, audit the exact generated selected variant.
    # These are structural claims with source-file SHA-256, NEVER an assertion
    # that the selected RTL elaborated or emitted accepted AXI traffic.
    if (test.get('report',{}).get('axi')
            and plan.get('top') in ('full_chip_tb','full_chip_dma_tb')
            and test.get('sources') == 'noc'):
        from variant_connectivity import publish as publish_variant_connectivity
        connectivity = publish_variant_connectivity(ROOT, name, plan, out)
        print(f'CONNECTIVITY {name}: {connectivity["summary"]["monitors"]} '
              f'AXI source taps, {connectivity["summary"]["declared_live_peripherals"]} '
              'declared live packet endpoints; not elaborated/observed', flush=True)
    runtime_selected = select_runtime(name,plan,out,commands=commands)
    save_runtime(selected_path,runtime_selected)
    runner_events = []
    def save_dispatch():
        # A command start is not a proof that its internal stimulus ran.
        (out/'runner-events.json').write_text(json.dumps({
            'schema_version':1,'target':name,
            'plan_sha256':runtime_selected['plan_sha256'],
            'events':runner_events},indent=2)+'\n')
    save_dispatch()
    env = dict(os.environ)
    env['SOC_RUN_PLAN'] = str(plan_file)
    if test.get('firmware_mode') in ('scenario_bfm', 'cpu_dma_scenario'):
        location = out/('variant' if test['firmware_mode']=='cpu_dma_scenario' else '')/'scenario-plan.json'
        if not location.is_file():
            raise ValueError('SCN-2 scenario plan missing before execution')
        env['SOC_SCENARIO_PLAN'] = str(location)
    else:
        env.pop('SOC_SCENARIO_PLAN', None)
    env['PYTHONPATH'] = str(ROOT) + os.pathsep + env.get('PYTHONPATH', '')
    env.pop('SUPERNOC_NEGATIVE', None)
    env.update(test.get('env', {}))
    started = time.monotonic()
    results = []
    for label, command in commands:
        print(f'RUN {name}/{label} ({engine}, stage={options.stage})', flush=True)
        runner_events.append(dispatch_event(runtime_selected,label,status='started'))
        save_dispatch()
        command_started = time.monotonic()
        try:
            code, timed_out = run_process(command, out/f'{label}.log',
                                          test.get('timeout_s', resolver.config['defaults']['timeout_s']), env)
        except (OSError, subprocess.SubprocessError) as exc:
            runner_events.append(dispatch_event(
                runtime_selected,label,status='completed',passed=False,
                duration_s=time.monotonic()-command_started,reason=str(exc)))
            save_dispatch()
            raise
        text = (out/f'{label}.log').read_text(errors='replace')
        if engine == 'cocotb-verilator':
            for collateral in ('build.log', 'simulation.log'):
                if (out/collateral).is_file():
                    text += '\n' + (out/collateral).read_text(errors='replace')
        expectation = {} if options.stage == 'build' or test.get('mode') == 'compile' else test
        ok, reason = check_outcome(code, text, expectation, timed_out)
        runner_events.append(dispatch_event(
            runtime_selected,label,status='completed',passed=ok,
            duration_s=time.monotonic()-command_started,reason=reason))
        save_dispatch()
        warnings = sum('[xezim][warning]' in line or '%Warning-' in line for line in text.splitlines())
        results.append({'name': label, 'passed': ok, 'exit_code': code, 'reason': reason, 'reported_warning_lines': warnings})
        print(f'{"PASS" if ok else "FAIL"} {name}/{label}: {reason}; warnings={warnings}; logs={out.relative_to(ROOT)}/', flush=True)
        if not ok:
            print('\n'.join(text.splitlines()[-30:]), flush=True)
    check_events(runtime_selected, runner_events)
    passed = all(r['passed'] for r in results)
    result = {'target': name, 'passed': passed, 'stage': options.stage,
              'identity_sha256': identity['identity_sha256'],
              'canonical_id': relative_path(identity).as_posix(),
              'elapsed_s': round(time.monotonic()-started, 3), 'results': results,
              'test_flow': {'status':'unmeasured','steps':0,'issues':0}}
    if test.get('report') and options.stage in ('all','run'):
        # The existing AXI report remains byte-for-byte compatible.
        # Other upstream VIPs feed a separate protocol-neutral capture.
        if 'axi' in test['report']:
            from axi_report import write_report
            summary = write_report(out,plan,result)
            axi_bad = (not summary['capture_bound'] or summary['overflow']
                       or summary['issues'] or not summary['transactions'])
        else:
            from protocol_report import build
            protocol_only = build(out, plan)
            summary = {'transactions':len(protocol_only['records']),
                       'capture_bound':protocol_only['capture_complete'],
                       'overflow':False,'issues':len(protocol_only['issues'])}
            axi_bad = False
            if (out/'protocols.html').exists():
                shutil.copyfile(out/'protocols.html',out/'report.html')
        if 'protocols' in test['report']:
            protocol_data = json.loads((out/'protocol-transactions.json').read_text())
            protocol_bad = (not protocol_data['capture_complete']
                            or not any(row['protocol']!='axi4' for row in protocol_data['records']))
        else:
            protocol_bad = False
        if passed and not test.get('expect_failure') and (axi_bad or protocol_bad):
            passed = result['passed'] = False
            results.append({'name':'protocol capture','passed':False,
                            'reason':'missing, incomplete or inconsistent protocol evidence'})
            print(f'FAIL {name}/protocol capture: missing, incomplete or inconsistent evidence',flush=True)
            if 'axi' in test['report']:
                write_report(out,plan,result)
        if 'fabric_benchmark' in test['report'] and passed:
            from fabric_benchmark import validate_files, BenchmarkError
            try:
                proof = validate_files(out)
                print(f'FABRIC_BENCHMARK {name}: {proof["measured_transactions"]} '
                      'accepted source transactions', flush=True)
            except (BenchmarkError, OSError, ValueError, KeyError, TypeError) as error:
                passed = result['passed'] = False
                results.append({'name':'fabric benchmark acceptance',
                                'passed':False,'reason':str(error)})
                print(f'FAIL {name}/fabric benchmark: {error}',flush=True)
        if 'flow' in test['report']:
            from test_flow_report import write_report as write_flow
            flow_result = write_flow(out, plan)
            # Bind real observed INIT/RUN/CHECK evidence to the immutable
            # pre-simulation selected declaration; report parsing and the
            # website must reject any mismatched run selection.
            flow_result['planned_flow_sha256']=selected['plan_sha256']
            (out/'test-flow.json').write_text(json.dumps(flow_result,indent=2)+'\n')
            result['test_flow'] = {'status':'complete' if flow_result['passed'] else 'incomplete',
                                   'passed':flow_result['passed'],
                                   'steps':len(flow_result['rows']),
                                   'issues':len(flow_result['issues'])}
            if not flow_result['passed']:
                passed = result['passed'] = False
                results.append({'name':'test-flow evidence','passed':False,
                                'reason':'missing, failed, incomplete or undeclared INIT/RUN/CHECK steps'})
                print(f'FAIL {name}/test-flow: {flow_result["issues"][:8]}',flush=True)
        # The run artifact is finalized only after the step-flow gate:
        # previously the AXI/protocol JSON embedded stale 'unmeasured'.
        if 'flow' in test['report']:
            import protocol_report
            latency_issues = protocol_report.finalize_run(out, result)
            if latency_issues:
                passed = result['passed'] = False
                results.append({'name':'PCIe/AXI/SRAM latency and data correlation',
                                'passed':False,'reason':'; '.join(latency_issues[:3])})
                print(f'FAIL {name}/traffic correlation: {latency_issues[:8]}',flush=True)
                protocol_report.finalize_run(out, result)
        print(f'REPORT {name}: {summary["transactions"]} observations; {out.relative_to(ROOT)}/report.html',flush=True)
    if (test.get('report',{}).get('flow') and passed
            and options.stage in ('all','run')):
        from runtime_contract import qualify_observed_phase_milestones, RunContractError
        try:
            milestone=qualify_observed_phase_milestones(runtime_selected,out,result=result)
            (out/'selected-flow-correlation.json').write_text(
                json.dumps(milestone,indent=2)+'\n')
        except (RunContractError,OSError,ValueError,TypeError) as exc:
            passed=result['passed']=False
            results.append({'name':'selected INIT/RUN/CHECK source contract',
                            'passed':False,'reason':str(exc)})
            print(f'FAIL {name}/selected phase correlation: {exc}',flush=True)
    if runtime_selected["adapter"]=="scenario_dispatch_adapter" and passed:
        from runtime_contract import qualify_selected_scenario, RunContractError
        try:
            qualify_selected_scenario(runtime_selected,out,result=result)
        except (RunContractError,OSError,ValueError,TypeError) as exc:
            passed=result['passed']=False
            results.append({'name':'selected scenario action correlation',
                            'passed':False,'reason':str(exc)})
            print(f'FAIL {name}/selected scenario action correlation: {exc}',flush=True)
    (out/'result.json').write_text(json.dumps(result, indent=2) + '\n')
    if (test.get('firmware_mode') in ('cpu_dma_scenario', 'scenario_bfm')
            and options.stage in ('all', 'run') and not test.get('expect_failure')):
        # The canonical run report exists; append the same verifiable
        # memory-lifetime table only after actual RTL/flow success. Avoid
        # treating the planner's allocations as observed CPU malloc tokens.
        from dv.common.action_events import ActionEvidenceError
        from scenario_memory_trace import finalize_scenario_run
        if passed:
            try:
                memory_view = finalize_scenario_run(
                    out, firmware_mode=test['firmware_mode'], result=result)
                print(f"MEMORY_LIFETIMES {name}: {memory_view['status']}; "
                      f"{len(memory_view['buffers'])} buffers", flush=True)
            except (ActionEvidenceError, OSError, ValueError, TypeError, KeyError) as error:
                passed = result['passed'] = False
                results.append({'name':'scenario memory lifetime evidence',
                                'passed':False,'reason':str(error)})
                (out/'result.json').write_text(json.dumps(result, indent=2) + '\n')
                print(f'FAIL {name}/memory lifetime evidence: {error}', flush=True)
    return passed


def main():
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument('targets', nargs='*', default=['full'])
    cli.add_argument('--config', type=Path, default=ROOT/'config/regression.yaml')
    cli.add_argument('--list', action='store_true')
    cli.add_argument('--explain', action='store_true', help='read-only test/build and selected RTL provenance (no Bender or simulator)')
    cli.add_argument('--check-noc', action='store_true')
    cli.add_argument('--fail-fast', action='store_true',
                     help='stop this suite at the first failing target (CI quick feedback)')
    cli.add_argument('--stage', choices=['files', 'build', 'run', 'all'], default='all')
    cli.add_argument('--memory-config')
    cli.add_argument('--network', action='append', default=[])
    cli.add_argument('--arg', action='append', default=[])
    options = cli.parse_args()
    config = load_config(options.config)
    targets = expand(config, options.targets)
    if options.explain:
        if (options.memory_config or options.network or options.arg
                or options.stage != 'all' or options.list or options.check_noc):
            raise ValueError('--explain is read-only; use --stage files for new exact inputs')
        from selected_rtl_provenance import explain_target
        explanations = [explain_target(ROOT, name, config["tests"][name], config)
                        for name in targets]
        print(json.dumps(explanations[0] if len(explanations) == 1
                         else explanations, indent=2))
        return 0
    if options.list:
        for name in targets:
            print(f'{name:22} {config["tests"][name]["engine"]}')
        return 0
    if options.check_noc:
        print(f'PASS: {len(noc_contracts())} configured NoC module/package/native contracts')
        return 0
    if options.memory_config and any(config['tests'][n]['sources'] != 'memory' for n in targets):
        raise ValueError('--memory-config applies only to memory targets')
    if options.stage == 'build' and any(config['tests'][n].get('reuse_build') for n in targets):
        raise ValueError('build stage must select the positive build target')
    print('Checking generated artifacts before resolving RTL...', flush=True)
    capture([sys.executable, str(ROOT/'tools/generate.py'), '--check'])
    resolver = Resolver(config)
    passed = True
    for name in targets:
        try:
            target_passed = run_target(name, config['tests'][name], resolver, options)
        except (ValueError, OSError, subprocess.SubprocessError) as error:
            print(f'FAIL {name}: {error}', file=sys.stderr, flush=True)
            target_passed = False
        if not target_passed:
            passed = False
            if options.fail_fast:
                print(f'STOP after {name}: subsequent suite targets skipped; '
                      'failing log and AXI report already preserved', flush=True)
                break
    return 0 if passed else 1


if __name__ == '__main__':
    try:
        sys.exit(main())
    except (ValueError, OSError, subprocess.SubprocessError) as error:
        sys.exit(str(error))
