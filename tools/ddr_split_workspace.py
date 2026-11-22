"""Strict same-checkout build/run continuation for the existing DDR-B regression."""
from __future__ import annotations

import json
import os
from pathlib import Path

try:
    from .test_identity import IdentityError, RUN, load, relative_path, selected, sha
except ImportError:
    from test_identity import IdentityError, RUN, load, relative_path, selected, sha

TARGET = "chip-ddr4-real"
DDR_MONITOR_CATALOG = "ddr_noc/supernoc/axi_monitors.json"
# Also consumed indirectly: the existing MRS checker reads the generated init
# plan from its pinned source location, and the report uses the captured CSR map.
DDR_INPUTS = (
    "ddr_noc/soc.yaml", "ddr_noc/ddr4_init_script.json",
    DDR_MONITOR_CATALOG, "ddr-native-csr-map.json",
    "variant/manifest.json", "variant/firmware.json",
)
PINNED_INPUTS = (
    ".tools/ddr4/litedram_sim/ddr4_init_plan.json",
    ".tools/ddr4/litedram_sim/ddr4_manifest.json",
    ".tools/ddr4/litedram_sim/csr.json",
    "rtl/memory/ddr4/toolchain.lock.yml", "tools/sim_cocotb.py",
    "dv/full_chip/test_ddr_real.py", "rtl/memory/ddr4/mrs_check.py",
)
BUILD_RECORDS = ("ddr-build-plan.json", "ddr-build-invocation.log", "build.log")
SEAL = "ddr-split-build.json"
CLAIM = "ddr-split-run.claim"
RUN_OUTPUTS = (
    CLAIM, "result.json", "results.xml", "simulation.log", "runner-events.json",
    "planned-flow.json", "selected-test-plan.json", "report.html",
    "axi-events.jsonl", "axi-transactions.json", "protocol-transactions.json",
    "test-flow.json", "ddr4_fullchip_evidence.json", "ddr4_mrs_evidence.json",
)


def eligible(name, test):
    return (name == TARGET and test.get('engine') == 'cocotb-verilator'
            and test.get('sources') == 'noc' and test.get('firmware_mode') == 'ddr_cpu_dma'
            and test.get('top') == 'full_chip_tb'
            and test.get('module') == 'dv.full_chip.test_ddr_real'
            and test.get('bender_targets') == ['chip_boot', 'dma']
            and not any(test.get(k) for k in ('reuse_build', 'boot_relocate',
                                            'memory_config', 'flow_plan')))


def plan_report(root, out, report):
    prefix = out.relative_to(root).as_posix()
    address = report['address_map']
    axi = report['axi']
    if (address.get('variant') != 'ddr_real'
            or (address.get('config'), address.get('csr_map'),
                axi.get('catalog'), axi.get('actors')) !=
               (DDR_INPUTS[0], DDR_INPUTS[3], DDR_INPUTS[2], DDR_INPUTS[4])):
        raise IdentityError('unreviewed DDR report input selection')
    return {**report, 'address_map': {**address,
                'config': f"{prefix}/{address['config']}",
                'csr_map': f"{prefix}/{address['csr_map']}"},
            'axi': {**axi, 'catalog': f"{prefix}/{axi['catalog']}",
                           'actors': f"{prefix}/{axi['actors']}"}}


def _owned(root, path):
    if (not path.is_relative_to(root)
            or any(p.is_symlink() for p in (path, *path.parents))
            or not path.is_file()):
        raise IdentityError('missing or unsafe DDR build input: ' + str(path))
    return path


def _data(root, path):
    return _owned(root, path).read_bytes()


def write_once(root, path, payload):
    if (not path.is_relative_to(root)
            or any(p.is_symlink() for p in (path, *path.parents))):
        raise IdentityError('unsafe DDR build record location')
    with path.open('xb') as stream:
        stream.write(payload)


def _state(root, out, plan):
    build = root / plan['build']
    stamp = build / 'regression-build.json'
    binary = build / plan['top']
    raw_stamp = _data(root, stamp)
    state = json.loads(raw_stamp)
    binary_sha = sha(_data(root, binary))
    if (not os.access(binary, os.X_OK) or not isinstance(state, dict)
            or state.get('binary_sha256') != binary_sha
            or not isinstance(state.get('signature'), str)):
        raise IdentityError('DDR binary disagrees with completed build stamp')
    return {**input_snapshot(root, out, plan), 'build_stamp_sha256': sha(raw_stamp),
            'binary_sha256': binary_sha,
            'build_records_sha256': {path: sha(_data(root, out/path)) for path in BUILD_RECORDS}}


def input_snapshot(root, out, plan):
    """Freeze collateral before build; mutable binary properties are added later."""
    return {
        'schema_version': 1,
        'identity_sha256': plan['identity']['identity_sha256'],
        'plan_sha256': sha(_data(root, out / 'plan.json')),
        'selected_manifest_sha256': sha(_data(root, out / 'selected-rtl-manifest.json')),
        'inputs_sha256': {path: sha(_data(root, out / path)) for path in DDR_INPUTS},
        'pinned_inputs_sha256': {path: sha(_data(root, root / path)) for path in PINNED_INPUTS},
    }


def seal(root, out, plan, prepared):
    state = _state(root, out, plan)
    if any(state.get(key) != value for key, value in prepared.items()):
        raise IdentityError('DDR selected inputs changed during build')
    write_once(root, out / SEAL, (json.dumps(state, sort_keys=True) + '\n').encode())


def bound_run_id(root, test, run_id):
    if not isinstance(run_id, str) or not RUN.fullmatch(run_id):
        raise IdentityError('DDR continuation requires an exact build run ID')
    partial = selected(TARGET, test, root=root, run_id=run_id)
    out = root / '.tools/runs' / relative_path(partial)
    data = _data(root, out / 'identity.json')
    identity = load(out / 'identity.json', target=TARGET, plan=test)
    ci_run = os.environ.get('GITHUB_RUN_ID')
    ci_attempt = os.environ.get('GITHUB_RUN_ATTEMPT', '1')
    invocation = f'ci-{ci_run}-a{ci_attempt}-' if ci_run is not None else 'local-'
    if not run_id.startswith(invocation):
        raise IdentityError('DDR build ID belongs to a different CI attempt')
    expected = selected(TARGET, test, root=root, run_id=run_id,
                        filelist_bytes=_data(root, out / 'sources.f'))
    if identity != expected or json.loads(data) != identity:
        raise IdentityError('DDR build sources or checkout locks are stale')
    return out, identity


def prepare_continuation(root, test, run_id, *, verify_archive, command, fingerprint):
    """Read and check the existing selection; never generate a fresh build."""
    out, identity = bound_run_id(root, test, run_id)
    plan = json.loads(_data(root, out / 'plan.json'))
    if (plan.get('target') != TARGET or plan.get('stage') != 'run'
            or plan.get('identity') != identity
            or plan.get('commands') != command(out / 'plan.json')
            or plan.get('results_xml') != str(out / 'results.xml')
            or plan.get('build') != str(Path(test['build']) / run_id)
            or plan.get('report') != plan_report(root, out, test['report'])):
        raise IdentityError('foreign DDR split execution plan')
    if any((out / name).exists() or (out / name).is_symlink() for name in RUN_OUTPUTS):
        raise IdentityError('DDR continuation has already started or contains run evidence')
    stored = json.loads(_data(root, out / SEAL))
    if stored != _state(root, out, plan):
        raise IdentityError('sealed DDR build/inputs changed before continuation')
    verify_archive(root, TARGET, test, directory=out)
    stamp = json.loads(_data(root, (root / plan['build']) / 'regression-build.json'))
    if stamp.get('signature') != fingerprint(plan):
        raise IdentityError('DDR compile inputs or simulator changed since build')
    # This is the only post-validation claim. An interrupted simulation gets
    # a new build ID rather than replacing any prior evidence.
    write_once(root, out / CLAIM, b'ddr-build-continuation-v1\n')
    return out, identity, plan
