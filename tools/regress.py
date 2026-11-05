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
          'build', 'reuse_build', 'env', 'seed', 'bender_targets', 'mode', 'report', 'firmware_mode'}


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
        if test.get('firmware_mode') not in (None, 'cpu_dma', 'pcie_host'):
            raise ValueError(f'{name}: unknown compiled CPU firmware mode')
        if 'firmware_mode' in test and (
            test['engine'] != 'cocotb-verilator' or
            'chip_boot' not in test.get('bender_targets', []) or
            (test['firmware_mode'] == 'cpu_dma'
             and 'dma' not in test.get('bender_targets', []))):
            raise ValueError(f'{name}: selected test needs real chip RTL and specified active IP')
        if 'report' in test:
            report = test['report']
            required = {'scope','clock','reset','catalog'}
            if (test['engine'] != 'cocotb-verilator' or not isinstance(report, dict)
                or not ({'axi','protocols'} & set(report))
                or set(report) - {'axi','protocols','memory','context','flow'}
                or ('context' in report and not isinstance(report['context'],str))):
                raise ValueError(f'{name}: invalid protocol report configuration for cocotb-verilator')
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
    if set(expand(config, ['full'])) != set(config['tests']):
        raise ValueError('full suite must cover every declared test')
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
    if test.get('firmware_mode') == 'cpu_dma':
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
        prepare_cpu_dma(cfg, noc_manifest, ROOT/'gen/noc/floonoc', variant)
        generated_root = ROOT/'gen/chip'
        replacements = {'soc_top.sv', 'full_chip_tb.sv', 'full_chip_dma_tb.sv'}
        sources = [str(variant/Path(filename).name)
                   if Path(filename).parent == generated_root and
                   Path(filename).name in replacements else filename
                   for filename in sources]
    if test.get('firmware_mode') == 'pcie_host':
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
    sources = list(dict.fromkeys(sources))
    includes = list(dict.fromkeys(includes))
    defines = list(dict.fromkeys(defines))
    filelist = out/'sources.f'
    filelist.write_text(filelist_text(sources, includes, defines))
    plan = {**test, 'target': name, 'sources': sources, 'includes': includes, 'defines': defines,
            'args': args, 'results_xml': str(out/'results.xml'), 'stage': options.stage}
    plan_file = out/'plan.json'
    plan_file.write_text(json.dumps(plan, indent=2) + '\n')
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
    env = dict(os.environ)
    env['SOC_RUN_PLAN'] = str(plan_file)
    env['PYTHONPATH'] = str(ROOT) + os.pathsep + env.get('PYTHONPATH', '')
    env.pop('SUPERNOC_NEGATIVE', None)
    env.update(test.get('env', {}))
    started = time.monotonic()
    results = []
    for label, command in commands:
        print(f'RUN {name}/{label} ({engine}, stage={options.stage})', flush=True)
        code, timed_out = run_process(command, out/f'{label}.log', test.get('timeout_s', resolver.config['defaults']['timeout_s']), env)
        text = (out/f'{label}.log').read_text(errors='replace')
        if engine == 'cocotb-verilator':
            for collateral in ('build.log', 'simulation.log'):
                if (out/collateral).is_file():
                    text += '\n' + (out/collateral).read_text(errors='replace')
        expectation = {} if options.stage == 'build' or test.get('mode') == 'compile' else test
        ok, reason = check_outcome(code, text, expectation, timed_out)
        warnings = sum('[xezim][warning]' in line or '%Warning-' in line for line in text.splitlines())
        results.append({'name': label, 'passed': ok, 'exit_code': code, 'reason': reason, 'reported_warning_lines': warnings})
        print(f'{"PASS" if ok else "FAIL"} {name}/{label}: {reason}; warnings={warnings}; logs={out.relative_to(ROOT)}/', flush=True)
        if not ok:
            print('\n'.join(text.splitlines()[-30:]), flush=True)
    passed = all(r['passed'] for r in results)
    result = {'target': name, 'passed': passed, 'stage': options.stage,
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
        if 'flow' in test['report']:
            from test_flow_report import write_report as write_flow
            flow_result = write_flow(out, plan)
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
    (out/'result.json').write_text(json.dumps(result, indent=2) + '\n')
    return passed


def main():
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument('targets', nargs='*', default=['full'])
    cli.add_argument('--config', type=Path, default=ROOT/'config/regression.yaml')
    cli.add_argument('--list', action='store_true')
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
