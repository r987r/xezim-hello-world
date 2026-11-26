"""Validate the original isolated connected-memory checker, not a traffic trace."""
import hashlib
import json
import re
import sys
from pathlib import Path

import yaml

from pcie_connected_roundtrip_evidence import check
from test_identity import relative_path, validate as validate_identity

WORKFLOW = 'pcie-connected-memory.yml'
JOB = 'Original Gen1 RC/EP, real bridge, generated NoC, SRAM and host CplD byte oracle'
STEPS = (
    'Compile original endpoint and RC with actual bridge, selected FlooNoC and SRAM',
    'Require original host BAR memory readback and independent SRAM evidence',
    'Archive original compiler, simulator and source-validated evidence even on failure',
)
TARGET = 'pcie-connected-memory'
SCOPE = 'isolated_connected_memory_roundtrip'
SPEC = 'config/scenarios/pcie-gen1-mem-ingress.json'
CONFIG = 'config/soc.yaml'
COMPILE_CWD = '.tools/pcie-connected-fusesoc/fusesoc_pcie_phy_core_1.0.0/sim'
FILES = frozenset(('identity.json', 'plan.json', 'sources.f', 'compiler-argv.json',
                   'scenario-plan.json', 'build.log', 'simulation.log',
                   'pcie-connected-memory-evidence.json'))
NEGATIVES = ('PCIE_CONNECTED_SRAM_DATA_OK:', 'PCIE_CONNECTED_EP_TX_CPLD:',
             'PCIE_RC_BAR_MRD_CPLD_PASS:', 'PCIE_CONNECTED_SRAM_READ:')
CANONICAL = re.compile(r'verilator/pcie-connected-memory-default/host-to-sram-roundtrip/ci-([0-9]+)-a([0-9]+)-[a-f0-9]{12}\Z')


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def require_job(run, jobs):
    matches = [j for j in jobs if j.get('name') == JOB]
    if len(matches) != 1:
        raise ValueError('missing or ambiguous dedicated connected job')
    job = matches[0]
    if ((run.get('status'), run.get('conclusion')) != ('completed', 'success')
            or (job.get('run_id'), job.get('run_attempt'), job.get('head_sha'))
            != (run['id'], run.get('run_attempt', 1), run['head_sha'])
            or (job.get('status'), job.get('conclusion')) != ('completed', 'success')
            or type(job.get('id')) is not int or job['id'] < 1):
        raise ValueError('dedicated connected job failed or is from a different attempt')
    for name in STEPS:
        matches = [s for s in job.get('steps', []) if s.get('name') == name]
        if len(matches) != 1 or (matches[0].get('status'), matches[0].get('conclusion')) != ('completed', 'success'):
            raise ValueError('required native connected step did not succeed: '+name)
    return job['id']


def matches_run(canonical, run):
    match = CANONICAL.fullmatch(canonical)
    return match and match.groups() == (str(run['id']), str(run.get('run_attempt', 1)))


def validate(folder, run, read_tracked, accepts_checkout):
    # Import via the same repository root as the CLI scenario planner.
    root = str(Path(__file__).resolve().parents[1])
    if root not in sys.path:
        sys.path.insert(0, root)
    from dv.common.scenario import canonical_json, resolve_scenario
    candidates = list(folder.rglob('identity.json'))
    if len(candidates) != 1:
        raise ValueError('expected one connected run identity')
    directory = candidates[0].parent
    if {p for p in folder.rglob('*') if p.is_file()} != {directory/f for f in FILES}:
        raise ValueError('unexpected connected archive files or missing original inputs')
    def raw(name):
        return (directory/name).read_bytes()
    def load(name):
        return json.loads(raw(name))
    identity, plan = load('identity.json'), load('plan.json')
    validate_identity(identity, plan=plan, target=TARGET)
    path = relative_path(identity)
    if directory.relative_to(folder) != path or not matches_run(path.as_posix(), run):
        raise ValueError('wrong connected workspace or CI attempt')
    tested = plan.get('source_revision')
    if (plan.get('identity') != identity or plan.get('dirty') is not False
            or plan.get('evidence_scope') != SCOPE or plan.get('compile_cwd') != COMPILE_CWD
            or not isinstance(tested, str) or not re.fullmatch('[a-f0-9]{40}', tested)
            or not accepts_checkout(tested)):
        raise ValueError('unverified connected checkout')
    config, spec = read_tracked(CONFIG, tested), read_tracked(SPEC, tested)
    expected = resolve_scenario(json.loads(spec), yaml.safe_load(config), source_revision=tested)
    scenario, sources = raw('scenario-plan.json'), raw('sources.f')
    if (identity['selection']['soc_sha256'] != digest(config)
            or canonical_json(expected).encode('ascii') != scenario):
        raise ValueError('connected scenario does not match exact tested sources')
    paths = sources.decode().splitlines()
    compiler = load('compiler-argv.json')
    argv = compiler['argv']
    start = argv.index(paths[0]) if paths and paths[0] in argv else -1
    required = ('axi_sram_target.sv','bar0_noc_translate.sv','pcie_axi_master.v',
                'f_VProc.v','tb_pcie_cross_link.sv')
    if (digest(sources) != identity['selection']['filelist_sha256']
            or compiler.get('source_sha256') != digest(sources)
            or not compiler['cwd'].endswith('/'+COMPILE_CWD) or start < 1
            or argv[start:start+len(paths)] != paths or argv[0] != 'verilator'
            or sum(p.startswith('src/') for p in paths) < 35
            or any(not any(p.endswith('/'+name) for p in paths) for name in required)
            or not any('/gen/noc/floonoc/' in p for p in paths)
            or '--Mdir' not in argv or argv.index('--Mdir')+1 == len(argv)
            or not argv[argv.index('--Mdir')+1].endswith('/.tools/pcie-connected-obj/'+identity['run_id'])
            or not {'-DPCIE_CONNECTED_MEM', '-GVERIFY_REAL_MEM_WRITE=1'}.issubset(argv)
            or 'PCIE_CONNECTED_COMPILE_OK:' not in raw('build.log').decode()):
        raise ValueError('connected compiler receipt does not match original inputs')
    log, verdict = raw('simulation.log').decode(), load('pcie-connected-memory-evidence.json')
    if (verdict != check(log) or not verdict['qualified_connected_memory_roundtrip']
            or not verdict['over_link_bar0_qualified']
            or f'PCIE_SCN_DRIVER: plan={digest(scenario)} action=write_bar0 stage=driver_done' not in log):
        raise ValueError('connected native transcript does not match qualified checker result or scenario')
    if any(m not in log or check(log.replace(m, 'OMITTED:'))['qualified_connected_memory_roundtrip'] for m in NEGATIVES):
        raise ValueError('connected transcript failed negative replay')
    return {'canonical_id': path.as_posix(), 'tested_sha': tested, 'sources': len(paths),
            'scenario_sha256': digest(scenario), 'files': {name: digest(raw(name)) for name in sorted(FILES)}}
