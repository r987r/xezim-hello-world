#!/usr/bin/env python3
"""Build the static GitHub Pages hub from repo sources and actual CI artifacts.

Evidence always retains its own workflow run, attempt and tested commit.
The builder never treats an older green run as current-source validation.
"""
import argparse
import base64
import binascii
from datetime import datetime, timezone
import hashlib
from html import escape
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import stat
import subprocess
import urllib.error
import urllib.parse
import urllib.request
import zipfile

from markdown_it import MarkdownIt
import yaml

from axi_report import render_report
from protocol_report import render as render_protocol_report
from test_flow_report import render_summary as render_test_flow
from test_intent import (catalog as intended_flow_catalog, plan as intended_flow_plan,
                         render as render_intended_flow, validate_snapshot)

ROOT=Path(__file__).resolve().parents[1]
FILES={'result.json','plan.json','sources.f','simulation.log','build.log','results.xml',
       'axi-transactions.json','axi-events.jsonl',
       'protocol-transactions.json','protocol-events.jsonl','memory-operations.json',
       'test-flow.json','test-flow-events.jsonl','traffic-latency.json',
       'ddr-native-csr-map.json','ddr4_fullchip_evidence.json','ddr4_mrs_evidence.json',
       'planned-flow.json','memory-lifetimes.json','scenario-execution.json','scenario-plan.json',
       'variant-connectivity.json','variant-topology.json','variant-chip-manifest.json',
       'selected-test-plan.json','runner-events.json','selected-flow-correlation.json',
       'identity.json','fabric-benchmark-plan.json','fabric-benchmark-evidence.json'}


def dump(path,data):
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(data,indent=2)+'\n')


class StripAuthRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        result=super().redirect_request(req,fp,code,msg,headers,newurl)
        if result is not None and urllib.parse.urlsplit(newurl).netloc!='api.github.com':
            result.remove_header('Authorization')
        return result


class GitHub:
    def __init__(self,repository,token=None):
        if not re.fullmatch(r'[\w.-]+/[\w.-]+',repository):
            raise ValueError('invalid repository')
        self.repository=repository
        self.token=token
        self.opener=urllib.request.build_opener(StripAuthRedirect())

    def request(self,path,method='GET',data=None,binary=False):
        if not path.startswith('/repos/'+self.repository+'/'):
            raise ValueError('request outside the selected repository')
        headers={'Accept':'application/vnd.github+json','User-Agent':'soc-verification-pages',
                 'X-GitHub-Api-Version':'2022-11-28'}
        if self.token: headers['Authorization']='Bearer '+self.token
        body=json.dumps(data).encode() if data is not None else None
        req=urllib.request.Request('https://api.github.com'+path,headers=headers,data=body,method=method)
        with self.opener.open(req,timeout=180 if binary else 60) as response:
            raw=response.read()
        return raw if binary else json.loads(raw) if raw else {}

    def pages(self):
        path='/repos/'+self.repository+'/pages'
        site=self.request(path)
        if site.get('build_type')!='workflow':
            self.request(path,'PUT',{'build_type':'workflow'})
            site=self.request(path)
        if site.get('build_type')!='workflow':
            raise ValueError('GitHub Pages must use the GitHub Actions publishing source')
        return site


def extract_archive(data,destination,config,digest=None,*,evidence_only=False):
    """Verify CI ZIP provenance and safely extract only useful regression evidence.

    Simulator object directories can be >1 GiB even for a small test.
    Selection happens *before* the expanded-size limit; we still inspect
    every member for traversal/symlinks, and never use discarded build files
    as evidence of a passing run.
    """
    if len(data)>config['max_archive_mib']*1024**2:
        raise ValueError('CI archive exceeds publication size limit')
    if digest and digest.startswith('sha256:') and hashlib.sha256(data).hexdigest()!=digest[7:]:
        raise ValueError('CI archive digest mismatch')
    import io
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        selected=[]
        for info in archive.infolist():
            path=PurePosixPath(info.filename)
            mode=info.external_attr>>16
            if path.is_absolute() or '..' in path.parts or '\\' in info.filename or stat.S_ISLNK(mode):
                raise ValueError('unsafe CI archive member')
            if evidence_only:
                # Reject simulator products and previously generated HTML: the
                # trusted Pages builder re-renders reports from checked JSON.
                base=path.name
                if base not in FILES and not base.endswith(('.log','.f')):
                    continue
                if any(part in ('obj_dir','sim_build','noc_build','full_chip_build') for part in path.parts):
                    continue
            selected.append(info)
        if sum(i.file_size for i in selected)>config['max_expanded_mib']*1024**2:
            raise ValueError('expanded CI archive exceeds publication size limit')
        archive.extractall(destination, members=selected)


def merged_main_pr_heads(client):
    """Map exact merged head SHA + source branch to PR number on main."""
    heads={}
    for page in range(1,6):
        prs=client.request(f'/repos/{client.repository}/pulls?state=closed&base=main&per_page=100&page={page}')
        for pr in prs:
            if pr.get('merged_at') and (pr.get('base') or {}).get('ref')=='main':
                head=pr.get('head') or {}
                if head.get('sha') and head.get('ref'):
                    heads[(head['sha'],head['ref'])]=pr['number']
        if len(prs)<100:
            break
    return heads


def verified_merged_pr(run,merged_heads):
    """GitHub may clear workflow_run.pull_requests after a PR merges."""
    if run.get('event')!='pull_request':
        return None
    return merged_heads.get((run.get('head_sha'),run.get('head_branch')))


def verified_pr_test_commit(client,run,tested_sha,cache=None):
    """Accept head SHA or GitHub's authentic temporary PR merge commit.

    For pull_request checkout@v4, GitHub tests refs/pull/N/merge rather than
    the PR head. The merge commit must have the exact tested PR head as its
    second parent. A trace still must match its CI run ID, attempt and clean
    source state; an arbitrary SHA in an artifact is never sufficient.
    """
    if tested_sha==run['head_sha']:
        return True
    if not run.get('verified_merged_pr') or not isinstance(tested_sha,str):
        return False
    if not re.fullmatch(r'[a-f0-9]{40}',tested_sha):
        return False
    cache={} if cache is None else cache
    key=(tested_sha,run['head_sha'])
    if key not in cache:
        try:
            commit=client.request(f'/repos/{client.repository}/git/commits/{tested_sha}')
            parents=[item['sha'] for item in commit.get('parents',[])]
            cache[key]=len(parents)==2 and parents[1]==run['head_sha']
        except (urllib.error.HTTPError, KeyError, TypeError, ValueError):
            cache[key]=False
    return cache[key]



def verified_pr_tree_equivalent(client, run, tested_sha, site_sha, cache=None):
    """Only a validated merged-PR test commit with the exact site Git tree.

    A GitHub temporary PR merge commit has a different SHA from the real
    main merge commit even when they contain *identical files*. Validate
    both authentic Git commit trees; never infer equivalence from PR number,
    filename, address map or the appearance of a passing run.
    """
    if (not run.get("verified_merged_pr")
            or not isinstance(tested_sha, str) or not isinstance(site_sha, str)
            or not re.fullmatch(r'[a-f0-9]{40}', site_sha)
            or not verified_pr_test_commit(client, run, tested_sha)):
        return False
    cache = {} if cache is None else cache
    for sha in (tested_sha, site_sha):
        if sha not in cache:
            try:
                obj = client.request(f'/repos/{client.repository}/git/commits/{sha}')
                tree = (obj.get('tree') or {}).get('sha')
                cache[sha] = tree if isinstance(tree, str) and re.fullmatch(r'[a-f0-9]{40}', tree) else None
            except (urllib.error.HTTPError, KeyError, TypeError, ValueError):
                cache[sha] = None
    return bool(cache[tested_sha]) and cache[tested_sha] == cache[site_sha]



# The equivalence fingerprint is a simulation *input* manifest, rather than
# a whole-repository commit SHA. Documentation and report presentation do not
# alter tested RTL, AXI traffic, clocks or the generated source files.
# All unlisted files remain fingerprinted (safe default).
FABRIC_EXCLUDED_PREFIXES = (
    'docs/', 'tests/', '.github/workflows/', 'tools/templates/site_',
    # Static schematic assets are not compiled into RTL or testbench executables.
    'gen/diagrams/',
    # The checked-in project/variant review tree contains byte-for-byte
    # copies of generated RTL for browsing. Bender selects gen/chip/soc_top.sv,
    # never gen/projects/**; Bender.yml and all active gen/chip/supernoc/NoC
    # sources remain fingerprinted. A changed *compiled* top still invalidates
    # latency, while adding a duplicate preview must not.
    'gen/projects/',
    # Staged DDR4 generation/test *not* in the active Bender NoC or chip
    # simulation source lists. Future integration changes the included
    # Bender/config/generated RTL input hashes and invalidates old evidence.
    'rtl/memory/ddr4/',
    # The standalone CSR backdoor hierarchy probe uses its own top/Verilator
    # workflow, not Bender's supernoc/chip_boot source selections.
    'dv/csr_runtime/',
)
FABRIC_EXCLUDED_FILES = {
    'README.md', 'AGENTS.md', 'tools/publish_site.py',
    'tools/fabric_report.py', 'tools/templates/site.html',
    'tools/templates/run_report.html',
    # Generation-control metadata is not an executable simulation input.
    # The benchmark's make check-generated gate verifies generated outputs,
    # and the authenticated Git tree still fingerprints every selected
    # gen/chip, gen/supernoc, NoC RTL, catalog and Bender file itself.
    'gen/manifest.json', 'tools/generate.py',
    # Source-selected RTL staging is a read-only review/attestation path,
    # not invoked by dv-fabric-latency's simulator or cocotb run.
    'tools/stage_selected_rtl.py',
    # Separate opt-in review builder. It invokes regress --stage files for
    # source staging; Fabric benchmark workflows run tools/regress.py directly
    # and never invoke this wrapper.
    'tools/build_hardware_variant.py',
    # Read-only CSR backdoor runtime and standalone opt-in probe are not
    # imported by the serial one-beat NoC/full-chip latency tests. Their
    # separate probe runs a distinct csr_runtime_tb top outside Bender.
    'tools/csr_runtime.py', 'tools/run_csr_runtime_probe.py',
    # Read-only architecture extraction and diagram rendering have no
    # simulator or AXI monitor runtime side effects.
    'tools/rtl_instance_parser.py', 'tools/design_explorer.py',
    'tools/signal_inventory.py', 'tools/signal_paths.py',
    'tools/design_elaborate.py', 'tools/design_netlist.py',
    'tools/noc_diagrams.py', 'tools/diagram_svg.py', 'tools/diagram_gen.py',
}
# CI execution jobs (tool versions and invocation) must also be identical.
# Trigger/scheduling-only edits do not alter simulated timing and are ignored.
FABRIC_EXECUTION_WORKFLOWS = ('floonoc-elab.yml', 'full-chip.yml', 'dv-fabric-latency.yml')
FABRIC_REQUIRED_INPUTS = frozenset({
    'config/soc.yaml', 'config/interface_contracts.yaml',
    'config/regression.yaml', 'config/ip.lock.yaml', 'config/fabric_latency.yaml',
    'dv/supernoc/test_supernoc.py', 'dv/supernoc/test_latency.py',
    'dv/common/fabric_latency.py', 'dv/common/axi_outstanding.py',
    'dv/full_chip/test_latency.py',
    'tools/fabric_benchmark.py', 'dv/full_chip/test_boot.py',
    'dv/common/axi_trace.py',
    'tools/memory_service.py', 'tools/memory_report.py',
    'tools/supernoc_gen.py', 'tools/floonoc_gen.py',
    'tools/axi_report.py', 'tools/regress.py', 'tools/sim_cocotb.py',
    'gen/supernoc/soc_noc.sv', 'gen/supernoc/axi_monitors.json',
    'gen/noc/floonoc/manifest.json', 'Bender.yml', 'Bender.lock',
    'requirements.txt',
})


def fabric_execution_fingerprint(client, commit_sha, cache=None):
    """SHA-256 of the Git-authenticated NoC simulation and RTL inputs.

    A changed config, generated RTL, AXI monitor, model, test, clock, toolchain
    pin or unexpected file invalidates reuse. Exclude only known
    non-executable files. Reject incomplete or malformed Git tree listings.
    """
    if not isinstance(commit_sha, str) or not re.fullmatch(r'[a-f0-9]{40}', commit_sha):
        return None
    cache = {} if cache is None else cache
    if commit_sha in cache:
        return cache[commit_sha]
    cache[commit_sha] = None
    try:
        commit = client.request(f'/repos/{client.repository}/git/commits/{commit_sha}')
        tree_sha = (commit.get('tree') or {}).get('sha')
        if not isinstance(tree_sha, str) or not re.fullmatch(r'[a-f0-9]{40}', tree_sha):
            return None
        tree = client.request(f'/repos/{client.repository}/git/trees/{tree_sha}?recursive=1')
        if tree.get('truncated') or not isinstance(tree.get('tree'), list):
            return None
        files = {}
        for item in tree['tree']:
            if item.get('type') != 'blob':
                continue
            path, blob_sha = item.get('path'), item.get('sha')
            if not isinstance(path, str) or not isinstance(blob_sha, str):
                return None
            if path in FABRIC_EXCLUDED_FILES or path.startswith(FABRIC_EXCLUDED_PREFIXES):
                continue
            if not re.fullmatch(r'[a-f0-9]{40}', blob_sha) or path in files:
                return None
            files[path] = blob_sha
        if not FABRIC_REQUIRED_INPUTS.issubset(files):
            return None
        workflow_jobs = {}
        for name in FABRIC_EXECUTION_WORKFLOWS:
            wf_path = '.github/workflows/' + name
            wf_sha = next((item['sha'] for item in tree['tree']
                           if item.get('path') == wf_path and item.get('type') == 'blob'), None)
            if not isinstance(wf_sha, str) or not re.fullmatch(r'[a-f0-9]{40}', wf_sha):
                return None
            blob = client.request(f'/repos/{client.repository}/git/blobs/{wf_sha}')
            if blob.get('encoding') != 'base64':
                return None
            workflow = yaml.safe_load(base64.b64decode(blob['content']).decode('utf-8'))
            if not isinstance(workflow, dict) or not isinstance(workflow.get('jobs'), dict):
                return None
            workflow_jobs[name] = workflow['jobs']
        blob_manifest = json.dumps({'files': files, 'jobs': workflow_jobs},
                                   sort_keys=True, separators=(',', ':')).encode()
        result = {'policy': 'fabric-execution-inputs-v2',
                  'digest': hashlib.sha256(blob_manifest).hexdigest(),
                  'file_count': len(files)}
        cache[commit_sha] = result
        return result
    except (urllib.error.HTTPError, KeyError, TypeError, ValueError, binascii.Error,
            UnicodeDecodeError, yaml.YAMLError):
        return None


def verified_fabric_execution_equivalent(client, run, tested_sha, site_sha, cache=None):
    """Accept equivalent RTL only from already trusted CI provenance."""
    if not isinstance(tested_sha, str) or not isinstance(site_sha, str):
        return False
    if run.get('head_branch') == 'main':
        if tested_sha != run.get('head_sha'):
            return False
    elif not verified_pr_test_commit(client, run, tested_sha):
        return False
    tested = fabric_execution_fingerprint(client, tested_sha, cache)
    published = fabric_execution_fingerprint(client, site_sha, cache)
    return bool(tested and published and tested == published)



TEST_WORKFLOW_COMMAND=re.compile(
    r"\b(?:pytest|unittest|iverilog|verilator|cocotb|regress\.py)\b|\bmake\s+(?:dv-|test|check-)",
    re.IGNORECASE)


def discover_test_workflows(root=ROOT):
    """Auto-discover CI checks and their canonical regression artifacts.

    Test workflows with no canonical results are still included in workflow
    history (status-only). Only workflows explicitly uploading regression
    paths can contribute per-target reports; no invented result.json files.
    """
    producers={}
    for file in sorted((root/".github/workflows").glob("*.yml")):
        if file.name in ("pages.yml", "publish-xezim.yml"):
            continue  # Site publishing and simulator release are not test suites.
        workflow=yaml.safe_load(file.read_text()) or {}
        if not isinstance(workflow, dict):
            continue
        artifacts=[]
        is_test=False
        for job in (workflow.get("jobs") or {}).values():
            if not isinstance(job, dict):
                continue
            for step in job.get("steps", []) or []:
                if not isinstance(step, dict):
                    continue
                command=str(step.get("run", ""))
                if TEST_WORKFLOW_COMMAND.search(command):
                    is_test=True
                if not str(step.get("uses", "")).startswith("actions/upload-artifact@"):
                    continue
                opts=step.get("with") or {}
                if ".tools/regression/" in str(opts.get("path", "")):
                    artifacts.append(str(opts.get("name", "")))
        if artifacts or is_test:
            producers[file.name]={"file":file.name,
                                  "label":str(workflow.get("name") or file.stem),
                                  "artifacts":artifacts}
    return producers

def select_workflow_runs(client, producers, merged_heads, history, *, max_pages=10):
    """Collect recent trusted history for EACH test workflow independently.

    A global latest-500 run window starves infrequent DDR/Ethernet/PCIe tests
    when agents trigger many unrelated jobs. Workflow-scoped pagination also
    bounds the number of archives to the configured history depth.
    """
    if history <= 0 or max_pages <= 0:
        raise ValueError("workflow history and pagination bounds must be positive")
    selected={name:[] for name in producers}
    notes=[]
    for name in producers:
        # The workflow file is a repository-controlled filename, not a URL
        # from an artifact or an Actions response.
        workflow_id=urllib.parse.quote(name, safe="")
        for page in range(1, max_pages+1):
            response=client.request(
                f"/repos/{client.repository}/actions/workflows/{workflow_id}/runs?per_page=100&page={page}")
            batch=response.get("workflow_runs", [])
            for raw in batch:
                if raw.get("path", "").split("/")[-1] != name:
                    continue
                merged_pr=verified_merged_pr(raw, merged_heads)
                if raw.get("head_branch") != "main" and merged_pr is None:
                    continue
                run=dict(raw)
                if merged_pr is not None:
                    run["verified_merged_pr"]=merged_pr
                selected[name].append(run)
                if len(selected[name]) >= history:
                    break
            if len(selected[name]) >= history or len(batch) < 100:
                break
        else:
            notes.append(f"{name}: trusted history truncated after {max_pages} workflow pages")
    return selected, notes


def authenticated_runner_revisions(client, run, artifact_folder, cache=None):
    """Attest #129's original selected commit, including no-AXI CI jobs.

    PR workflows may checkout refs/pull/N/merge; the *actual Git commit*
    must be a verified GitHub merge with the CI PR head as second parent.
    A malformed snapshot or foreign checkout is NEVER repaired by replacing
    its source SHA with today's main. The caller quarantines the archive.
    """
    from runtime_contract import load as load_runner_selection
    verified=set()
    for file in sorted(artifact_folder.rglob('selected-test-plan.json')):
        try:
            snapshot=load_runner_selection(file)
            tested=snapshot['source_revision']
        except (ValueError,TypeError,KeyError,OSError) as exc:
            raise ValueError(f'invalid selected runner snapshot: {exc}') from exc
        if run.get('head_branch')=='main':
            accepted=tested==run.get('head_sha')
        else:
            accepted=verified_pr_test_commit(client,run,tested,cache)
        if not accepted:
            raise ValueError(f'original runner checkout not authenticated: {tested}')
        verified.add(tested)
    return verified


def verify_archived_identity(source_dir, plan, result, target, run):
    """Authenticate the original run-local identity without reconstructing it.

    This single contract is checked when first collecting an archive and
    again before publishing it, including direct/offline evidence builds.
    Legacy runs with no claimed identity retain their historical path.
    """
    from test_identity import load as load_identity, relative_path as canonical_path
    identity_file=source_dir/'identity.json'
    selected=(load_identity(identity_file,target=target,plan=plan)
              if identity_file.is_file() else None)
    if selected is not None:
        if (plan.get('identity')!=selected
                or result.get('identity_sha256')!=selected['identity_sha256']
                or result.get('canonical_id')!=canonical_path(selected).as_posix()):
            raise ValueError('archived run identity differs from original plan/result')
        expected_filelist=selected['selection'].get('filelist_sha256')
        if expected_filelist is not None:
            original_list=source_dir/'sources.f'
            if (not original_list.is_file()
                    or hashlib.sha256(original_list.read_bytes()).hexdigest()!=expected_filelist):
                raise ValueError('original archived source filelist differs from selected identity')
        prefix=f"ci-{run['id']}-a{run.get('run_attempt',1)}-"
        if selected['run_id'].startswith('ci-') and not selected['run_id'].startswith(prefix):
            raise ValueError('canonical run ID refers to a different CI attempt')
    elif (plan.get('identity') is not None
          or result.get('identity_sha256') is not None
          or result.get('canonical_id') is not None):
        raise ValueError('archived run identity source missing')
    return selected


def invalid_artifact_identity_provenance(artifact_folder, run):
    """Quarantine an entire incomplete identity archive, not the whole site.

    A missing identity.json cannot be synthesized from a plan/result: doing
    so would relabel unauthenticated evidence as current-source proof.
    """
    for result_path in sorted(artifact_folder.rglob('result.json')):
        relative=result_path.relative_to(artifact_folder).as_posix()
        try:
            result=json.loads(result_path.read_text())
            plan_file=result_path.parent/'plan.json'
            plan=json.loads(plan_file.read_text()) if plan_file.is_file() else {}
            if not isinstance(result,dict) or not isinstance(plan,dict):
                raise ValueError('archived plan/result must be JSON objects')
            verify_archived_identity(result_path.parent,plan,result,
                                     result.get('target'),run)
        except (ValueError, KeyError, TypeError, UnicodeError, OSError) as exc:
            return f'{relative}: {exc}'
    return None


def invalid_artifact_trace_provenance(artifact_folder, run):
    """Reject an untrustworthy capture *before* copying it into Pages.

    A historical run is allowed in the run list, but its trace bytes only
    appear as observed evidence if source, clean-state, CI run and attempt
    match the exact authenticated workflow metadata. Never rewrite an
    invalid trace to manufacture a pass or a "current" source SHA.
    """
    allowed=set(run.get('verified_tested_shas',[])) | {run['head_sha']}
    for basename in ('axi-transactions.json','protocol-transactions.json'):
        for trace in sorted(artifact_folder.rglob(basename)):
            relative=trace.relative_to(artifact_folder).as_posix()
            try:
                payload=json.loads(trace.read_text())
                actual=payload.get('run',{})
                if not isinstance(actual,dict):
                    raise ValueError('run provenance must be an object')
            except (ValueError,TypeError,UnicodeError,OSError) as exc:
                return f'{relative}: invalid JSON / provenance structure ({exc})'
            commit=actual.get('commit')
            if not isinstance(commit,str) or commit not in allowed:
                return (f'{relative}: tested SHA mismatch: recorded={commit!r}, '
                        f'expected one of {sorted(allowed)}')
            if actual.get('dirty') is not False:
                return f'{relative}: dirty/missing clean-source assertion'
            if str(actual.get('workflow_run_id')) != str(run['id']):
                return (f'{relative}: workflow_run_id mismatch: '
                        f"recorded={actual.get('workflow_run_id')!r}, expected={run['id']}")
            expected=run.get('run_attempt',1)
            if str(actual.get('workflow_attempt'))!=str(expected):
                return (f'{relative}: workflow_attempt mismatch: '
                        f"recorded={actual.get('workflow_attempt')!r}, expected={expected}")
    return None


def collect(client,config,destination):
    destination.mkdir(parents=True,exist_ok=True)
    producers=discover_test_workflows()
    merged_heads=merged_main_pr_heads(client)
    selected,notes=select_workflow_runs(
        client,producers,merged_heads,config["history_per_workflow"],
        max_pages=config.get("max_history_pages_per_workflow",10))
    site_sha=subprocess.check_output(["git","rev-parse","HEAD"],cwd=ROOT,text=True).strip()
    tree_cache={}
    fabric_cache={}
    # Publish only main or exact merged-PR source; PR artifact bytes are
    # never executed by this trusted Pages job.

    verified_cache={}
    for workflow in producers.values():
        for run in selected[workflow['file']]:
            folder=destination/(str(run['id'])+'-'+str(run.get('run_attempt',1)))
            folder.mkdir(parents=True,exist_ok=True)
            dump(folder/'workflow.json',workflow)
            if run['status']!='completed':
                dump(folder/'run.json',run)
                continue
            artifacts=client.request(f'/repos/{client.repository}/actions/runs/{run["id"]}/artifacts?per_page=100')['artifacts']
            # Only collect named regression archives uploaded by this CI workflow.
            for artifact in artifacts:
                allowed=workflow['artifacts']
                if not any(artifact['name']==pattern or
                           ('${' in pattern and artifact['name'].startswith(pattern.split('${',1)[0]))
                           for pattern in allowed):
                    continue
                if artifact.get('size_in_bytes',0)>config['max_archive_mib']*1024**2:
                    notes.append(f'Run {run["id"]}: archive too large {artifact["name"]}')
                    continue
                if artifact['expired']:
                    notes.append(f'Run {run["id"]}: expired artifact {artifact["name"]}')
                    continue
                target=folder/('artifact-'+str(artifact['id']))
                if not (target/'.complete').exists():
                    raw=client.request(f'/repos/{client.repository}/actions/artifacts/{artifact["id"]}/zip',binary=True)
                    target.mkdir(exist_ok=True)
                    extract_archive(raw,target,config,artifact.get('digest'),evidence_only=True)
                    (target/'.complete').write_text('verified\n')
                # A partially archived immutable run identity is not a
                # publishable legacy result. Exclude that archive while
                # retaining other independent, source-verified CI artifacts.
                invalid=invalid_artifact_identity_provenance(target,run)
                if invalid:
                    shutil.rmtree(target)
                    notes.append(
                        f'Run {run["id"]}, artifact {artifact["name"]}: '
                        f'excluded unverified identity ({invalid})')
                    # CI logs must show which archive was quarantined, not
                    # just a generic downstream "Unmeasured" state.
                    print("PUBLICATION QUARANTINE: " + notes[-1], flush=True)
                    continue
                try:
                    runner_revisions=authenticated_runner_revisions(
                        client,run,target,verified_cache)
                except ValueError as exc:
                    shutil.rmtree(target)
                    notes.append(f'Run {run["id"]}, artifact {artifact["name"]}: '
                                 f'excluded unverified runner source ({exc})')
                    continue
                if run.get('verified_merged_pr') is not None:
                    verified=set(run.get('verified_tested_shas',[])) | runner_revisions
                    invalid=None
                    for trace_file in [*target.rglob('axi-transactions.json'), *target.rglob('protocol-transactions.json')]:
                        trace_run=json.loads(trace_file.read_text()).get('run',{})
                        tested_sha=trace_run.get('commit')
                        if not verified_pr_test_commit(client,run,tested_sha,verified_cache):
                            invalid=f'PR merge commit not verifiable: {tested_sha}'
                            break
                        verified.add(tested_sha)
                        if verified_pr_tree_equivalent(client,run,tested_sha,site_sha,tree_cache):
                            matches=run.setdefault('verified_equivalent_site_shas',{})
                            matches[tested_sha]=site_sha
                    if invalid:
                        # Do not publish artifacts with unverified tested SHAs.
                        shutil.rmtree(target)
                        notes.append(f'Run {run["id"]}, artifact {artifact["name"]}: excluded ({invalid})')
                        continue
                    run['verified_tested_shas']=sorted(verified)
                # One legacy/incorrectly relabeled CI artifact must never
                # hide unrelated verified tests or take the full hub offline.
                # Keep the strict provenance contract: quarantine the entire
                # offending archive and expose the cause in publication notes.
                invalid=invalid_artifact_trace_provenance(target,run)
                if invalid:
                    shutil.rmtree(target)
                    notes.append(
                        f'Run {run["id"]}, artifact {artifact["name"]}: '
                        f'excluded unverified capture ({invalid})')
                    continue
                # For clean CI captures, attest execution-input equivalence
                # against the current published source using authenticated Git
                # blob IDs. Never infer that a changed RTL still has old timing.
                for trace_file in target.rglob('axi-transactions.json'):
                    trace_run=json.loads(trace_file.read_text()).get('run',{})
                    tested_sha=trace_run.get('commit')
                    if (trace_run.get('dirty') is False
                            and str(trace_run.get('workflow_run_id'))==str(run['id'])
                            and str(trace_run.get('workflow_attempt'))==str(run.get('run_attempt',1))
                            and verified_fabric_execution_equivalent(
                                client,run,tested_sha,site_sha,fabric_cache)):
                        run.setdefault('verified_equivalent_fabric_shas',{})[tested_sha]=site_sha
                dump(folder/('artifact-'+str(artifact['id'])+'.json'),artifact)
            dump(folder/'run.json',run)
    dump(destination/'collection.json',{'notes':notes})



def protocol_link_catalog(protocol_data, *, preview_per_source=12):
    """Build a bounded protocol-neutral index from verified monitor records.

    Protocol-specific fields remain opaque data owned by the VIP adapter.
    Bindings are source IDs, not inferred PHY wires or elaborated connectivity.
    """
    if not protocol_data:
        return None
    sources = {item['id']: item for item in protocol_data.get('sources', [])
               if isinstance(item, dict) and isinstance(item.get('id'), str)}
    indexed = {}
    for row in protocol_data.get('records', []):
        source = row.get('source')
        if source not in sources or row.get('kind') not in ('transaction', 'event'):
            continue
        group = indexed.setdefault(source, {
            'source': source, 'protocol': sources[source]['protocol'],
            'role': sources[source].get('role', 'unknown'),
            'clock_domain': sources[source].get('clock_domain', 'unknown'),
            'implementation': sources[source].get('implementation', 'unrecorded'),
            'count': 0, 'operations': {}, 'preview': []
        })
        group['count'] += 1
        operation = row.get('operation', 'unknown')
        group['operations'][operation] = group['operations'].get(operation, 0) + 1
        if len(group['preview']) < preview_per_source:
            group['preview'].append({
                'kind': row['kind'], 'operation': operation,
                'id': row.get('id'), 'start_ps': row.get('start_ps'),
                'end_ps': row.get('end_ps'), 'status': row.get('status'),
                # Bounded rows only; preserve native, protocol-specific fields
                # (PCIe tags/headers/bytes, Ethernet EtherType, APB regs,
                # AXI5 transaction attributes) without parsing or inference.
                'fields': row.get('fields', {})
            })
    return {'capture_complete': protocol_data.get('capture_complete') is True,
            'sources': list(indexed.values())} if indexed else None


def evidence_index(evidence,output,repository):
    runs,entries,notes=[],[],[]
    if (evidence/'collection.json').exists():notes=json.loads((evidence/'collection.json').read_text()).get('notes',[])
    for file in sorted(evidence.glob('*/run.json')):
        source=json.loads(file.read_text())
        workflow=json.loads((file.parent/'workflow.json').read_text())
        run={k:source.get(k) for k in ('id','name','status','conclusion','head_sha','head_branch','run_attempt','html_url','created_at','updated_at','path')}
        run['label']=workflow['label']
        verified_shas=set(source.get('verified_tested_shas',[]))
        # The PR head is not necessarily the commit the runner checked out.
        run['tested_sha']=(next(iter(verified_shas)) if len(verified_shas)==1 else run['head_sha'])
        if run['head_branch']!='main':
            number=source.get('verified_merged_pr')
            if source.get('event')!='pull_request' or type(number) is not int or number<=0:
                raise ValueError('publication cache contains unverified non-main run')
            run['merged_pr']=number
        runs.append(run)
        found=set()
        for result_path in sorted(file.parent.glob('artifact-*/**/result.json')):
            result=json.loads(result_path.read_text())
            target=result.get('target','')
            if not isinstance(target,str) or not re.fullmatch(r'[a-z][a-z0-9-]*',target):
                raise ValueError('invalid target in CI result artifact')
            if target in found:raise ValueError('duplicate target evidence in one workflow run')
            found.add(target)
            source_dir=result_path.parent
            plan=json.loads((source_dir/'plan.json').read_text()) if (source_dir/'plan.json').exists() else {}
            # Verify immutable identity BEFORE determining the artifact layout:
            # a canonical writer's leaf is a unique run_id, not its legacy
            # target. Accept it only when the original identity matches both
            # plan/result and the last four directory components. Old target-
            # named archives retain their original acceptance policy.
            from test_identity import relative_path as canonical_path
            selected_identity=verify_archived_identity(source_dir,plan,result,target,run)
            legacy_location=(target==source_dir.name or
                             re.fullmatch(r'artifact-[0-9]+',source_dir.name) is not None)
            canonical_location=(selected_identity is not None and
                                tuple(source_dir.parts[-4:])==
                                canonical_path(selected_identity).parts)
            if not (legacy_location or canonical_location):
                raise ValueError('invalid target in CI result artifact')
            # Canonical names are the *only* published paths for new runs.
            # Historical captures lack immutable identity and stay under their
            # original verified run/target path for explicit comparison.
            relative=(Path('runs')/canonical_path(selected_identity)
                      if selected_identity is not None else
                      Path('runs')/(str(run['id'])+'-'+str(run.get('run_attempt',1)))/target)
            destination=output/relative
            if destination.exists():
                raise ValueError('duplicate published canonical run or historical evidence path')
            destination.mkdir(parents=True,exist_ok=False)
            assets=[]
            for item in source_dir.iterdir():
                if item.is_file() and (item.name in FILES or item.suffix in ('.log','.f')):
                    shutil.copyfile(item,destination/item.name);assets.append(item.name)
            # Benchmark-run publication must retain and independently check
            # the selected cases against original passive AXI transactions.
            # Merely emitting a planned benchmark cannot populate timing.
            if plan.get('report',{}).get('fabric_benchmark') and result.get('passed') is True:
                from fabric_benchmark import validate as validate_fabric
                selected_bench=source_dir/'fabric-benchmark-plan.json'
                verified_bench=source_dir/'fabric-benchmark-evidence.json'
                if not selected_bench.is_file() or not verified_bench.is_file():
                    raise ValueError('passing latency benchmark lacks complete proof')
                stored=json.loads(verified_bench.read_text())
                original=json.loads((source_dir/'axi-transactions.json').read_text())
                checked=validate_fabric(original,json.loads(selected_bench.read_text()))
                if checked!=stored or stored.get('scope')!=target:
                    raise ValueError('archived latency benchmark proof disagrees with accepted AXI')
            trace_path=source_dir/'axi-transactions.json'
            trace=json.loads(trace_path.read_text()) if trace_path.exists() else None
            protocol_path=source_dir/'protocol-transactions.json'
            protocol_data=json.loads(protocol_path.read_text()) if protocol_path.exists() else None
            # Trust MRS only if this exact artifact's independent scoreboard
            # agrees with its separately captured DFI protocol events.
            mrs_path=source_dir/'ddr4_mrs_evidence.json'
            mr_view=None
            if mrs_path.is_file():
                if not protocol_path.is_file() or result.get('passed') is not True:
                    raise ValueError('unqualified DDR4 MR evidence without passing protocol capture')
                from ddr_mr_report import read_evidence
                mr_view=read_evidence(mrs_path,protocol_path)
                if target not in ('chip-ddr4-real','chip-ethernet-ddr-pcie'):
                    raise ValueError('DDR4 MRS artifact belongs to an unrelated target')
            flow_path=source_dir/'test-flow.json'
            flow_data=json.loads(flow_path.read_text()) if flow_path.exists() else None
            # Runner dispatch is a separate factual command-bound envelope, not
            # a competing intended-flow viewer or proof of internal actions.
            selected_correlation=source_dir/'selected-flow-correlation.json'
            selected_path=source_dir/'selected-test-plan.json'
            runner_path=source_dir/'runner-events.json'
            from runtime_contract import load as load_selected_plan, check_events
            runtime_selected=(load_selected_plan(selected_path,target)
                              if selected_path.is_file() else None)
            if selected_correlation.is_file():
                correlated=json.loads(selected_correlation.read_text())
                if (runtime_selected is None or result.get('passed') is not True
                        or correlated.get('status')!='observed_required_milestones'
                        or correlated.get('plan_sha256')!=runtime_selected['plan_sha256']
                        or correlated.get('evidence_kind')!=
                           'observed_flow_milestones_not_all_internal_actions'):
                    raise ValueError('historical selected flow correlation is not source-qualified')
            if runtime_selected is not None:
                if (runtime_selected.get('identity_sha256') !=
                        (selected_identity['identity_sha256'] if selected_identity else None)):
                    raise ValueError('selected runner plan and canonical run identity disagree')
                if (runtime_selected.get('source_revision') not in verified_shas | {run['head_sha']}
                        or runtime_selected.get('engine')!=plan.get('engine')
                        or runtime_selected.get('stage')!=plan.get('stage')):
                    raise ValueError('selected historical command plan disagrees with tested run')
                if runner_path.is_file():
                    runner_data=json.loads(runner_path.read_text())
                    if (runner_data.get('target')!=target or
                            runner_data.get('plan_sha256')!=runtime_selected['plan_sha256']):
                        raise ValueError('runner dispatch fingerprint differs from selected plan')
                    if len(runner_data.get('events',[])) == 2*len(runtime_selected['command_argv']):
                        check_events(runtime_selected,runner_data['events'])
                    elif result.get('passed') is True:
                        raise ValueError('passing run lacks complete command dispatch events')
                elif result.get('passed') is True and runtime_selected['command_argv']:
                    raise ValueError('passing run lacks observed command dispatch')
            latency_path=source_dir/'traffic-latency.json'
            latency_data=json.loads(latency_path.read_text()) if latency_path.exists() else None
            variant_view=None
            variant_graph=None
            view_file=source_dir/'variant-connectivity.json'
            if view_file.is_file():
                from variant_connectivity import render_html as render_variant_html
                variant_view=json.loads(view_file.read_text())
                variant_graph=json.loads((source_dir/'variant-topology.json').read_text())
                manifest_bytes=(source_dir/'variant-chip-manifest.json').read_bytes()
                orig_manifest=variant_view.get('source_manifest')
                names=variant_view.get('source_sha256') or {}
                expected_manifest_hash=names.get(orig_manifest)
                if (variant_view.get('schema_version')!=1
                        or variant_view.get('target')!=target
                        or variant_view.get('top')!=plan.get('top')
                        or variant_view.get('elaborated') is not False
                        or variant_view.get('observed_protocol_traffic') is not False
                        or variant_view.get('source_proof')!=
                           'generator_manifest_plus_selected_RTL_filelist_plus_actual_AXImon_taps_not_elaboration'
                        or not isinstance(expected_manifest_hash,str)
                        or hashlib.sha256(manifest_bytes).hexdigest()!=expected_manifest_hash):
                    raise ValueError('variant inventory source provenance or selected manifest mismatch')
                source_chip=json.loads(manifest_bytes)
                if (source_chip.get('top')!='soc_top'
                        or plan.get('top') not in (source_chip.get('testbench'),
                                                   source_chip.get('dma_testbench'))):
                    raise ValueError('variant chip source does not match selected testbench')
                if (variant_graph.get('variant_source_manifest_sha256')!=expected_manifest_hash
                        or variant_graph.get('variant_top_source_sha256') !=
                           names.get(variant_view.get('selected_soc_top'))
                        or variant_graph.get('status')!='selected_generated_variant_topology_not_elaborated'):
                    raise ValueError('variant 2D diagram differs from selected RTL/source manifest')
                configured_protocol_sources=variant_view.get('protocol_sources') or []
                if configured_protocol_sources and result.get('passed') is True:
                    if not protocol_data or protocol_data.get('capture_complete') is not True:
                        raise ValueError('passing variant has no complete required native protocol capture')
                    actual_sources={r['id']:r for r in protocol_data.get('sources',[])}
                    for declared in configured_protocol_sources:
                        observed=actual_sources.get(declared['id'])
                        if observed is None or any(
                                observed.get(key)!=declared.get(key)
                                for key in ('protocol','clock_domain','role','implementation','modeling')):
                            raise ValueError('passing native protocol source differs from selected YAML catalog')
                records=variant_view.get('boundaries')
                if (not isinstance(records,list) or
                        len(records)!=variant_view.get('summary',{}).get('monitors')
                        or len({r.get('id') for r in records})!=len(records)
                        or trace is None or
                        {r['id'] for r in records} !=
                        {m['id'] for m in trace['sections']['axi']['monitors']}):
                    raise ValueError('variant AXI monitor inventory differs from accepted per-run report')
            # Memory lifetimes must be re-derived from actual archived RTL
            # run inputs before being displayed. Never trust artifact HTML or
            # an unverified memory-lifetimes.json at face value.
            memory_view=None
            memory_file=source_dir/'memory-lifetimes.json'
            if memory_file.is_file():
                from scenario_memory_trace import build as build_memory
                mode=plan.get('firmware_mode')
                if mode not in ('cpu_dma_scenario','scenario_bfm') or result.get('passed') is not True:
                    raise ValueError('memory lifetime artifact from unqualified scenario')
                original_plan=(source_dir/'variant/scenario-plan.json'
                               if mode=='cpu_dma_scenario' else source_dir/'scenario-plan.json')
                execution_file=source_dir/'scenario-execution.json'
                if (not original_plan.is_file() or not execution_file.is_file()
                        or trace is None):
                    raise ValueError('memory lifetime artifact lacks its original run inputs')
                memory_view=build_memory(
                    original_plan.read_bytes(),axi=trace,
                    execution=json.loads(execution_file.read_text()),result=result)
                if memory_view != json.loads(memory_file.read_text()):
                    raise ValueError('archived memory lifetime table differs from verified evidence')
                shutil.copyfile(original_plan,destination/'scenario-plan.json')
            if flow_data is not None:
                planned=plan.get('report',{}).get('flow',{}).get('required_steps')
                status=result.get('test_flow',{})
                if (flow_data.get('schema_version')!=1 or
                        flow_data.get('expected_steps')!=planned or
                        flow_data.get('passed') is not status.get('passed') or
                        len(flow_data.get('rows',[])) != status.get('steps')):
                    raise ValueError('test-flow JSON disagrees with verified regression plan/result')
                render_test_flow(flow_data,destination/'test-flow.html')
            # Preserve source-selected per-run declared intent. Never load
            # the current website's scenario definition into historical runs:
            # the tested revision may have selected different actions/args.
            archived=source_dir/'planned-flow.json'
            if archived.is_file():
                declared=json.loads(archived.read_text())
                intended=validate_snapshot(declared,target=target)
                snapshot_status='captured_before_simulation'
                declared_hash=declared['plan_sha256']
            else:
                # Legacy archives lack selected plans. Show only the exact
                # regression metadata present in that archive, never today's
                # scenario actions or a fictitious dispatch record.
                intended=intended_flow_plan(target,plan)
                snapshot_status='legacy_run_selection_not_archived'
                declared_hash=None
            if flow_data is not None:
                observed_hash=flow_data.get('planned_flow_sha256')
                if declared_hash is not None and observed_hash != declared_hash:
                    raise ValueError('observed test-flow evidence references a different selected plan')
                if declared_hash is None and observed_hash is not None:
                    raise ValueError('observed test-flow SHA lacks original archived plan')
            dump(destination/'test-intent.json',intended)
            if latency_data is not None and (
                    not protocol_data or protocol_data.get('latency')!=latency_data):
                raise ValueError('published PCIe latency summary differs from verified protocol report')
            if protocol_data and protocol_data.get('latency') and latency_data is None:
                raise ValueError('PCIe latency evidence file missing')
            entry={'target':target,'engine':plan.get('engine','unknown'),'passed':result.get('passed') is True,
                   'fabric_scope':(plan.get('report') or {}).get('fabric_scope','unspecified'),
                   'expected_failure':plan.get('expect_failure'),'stage':result.get('stage'),
                   'run_id':run['id'],'attempt':run.get('run_attempt',1),'source_sha':run['tested_sha'],
                   'canonical_id':canonical_path(selected_identity).as_posix() if selected_identity else None,
                   'config_target':selected_identity['config_target'] if selected_identity else None,
                   'testname':selected_identity['testname'] if selected_identity else None,
                   'simulator':selected_identity['simulator'] if selected_identity else None,
                   'execution_id':selected_identity['run_id'] if selected_identity else None,
                   'identity_status':'source_verified' if selected_identity else 'historical_not_recorded',
                   'pr_head_sha':run['head_sha'],'merged_pr':run.get('merged_pr'),
                   'recorded_at':run['created_at'],'workflow':run['label'],'workflow_url':run['html_url'],
                   'path':str(relative/'report.html'),'assets':sorted(assets),
                   'axi':trace is not None,
                   'protocols':sorted({r['protocol'] for r in protocol_data.get('records',[])}) if protocol_data else [],
                   'protocol_observations':len(protocol_data['records']) if protocol_data else 0,
                   'flow_steps':len(flow_data['rows']) if flow_data else 0,
                   'variant_connectivity':variant_view is not None,
                   'variant_chip_profile':variant_view.get('chip_variant') if variant_view else None,
                   'memory_lifetimes':memory_view is not None,
                   'ddr_mrs_status':mr_view['status'] if mr_view else 'unmeasured',
                   'ddr_mrs_writes':mr_view['observed_writes'] if mr_view else None,
                   'selected_plan_sha256':runtime_selected['plan_sha256'] if runtime_selected else None,
                   'runtime_adapter':runtime_selected['adapter'] if runtime_selected else 'historical_unrecorded',
                   'planned_flow_status':snapshot_status,'planned_flow_sha256':declared_hash,
                   'planned_flow_intent':intended if declared_hash is not None else None,
                   'pcie_latency_measured':bool(latency_data and latency_data.get('passed')),
                   'result':result}
            if selected_identity is not None:
                # No by-test alias or competing legacy report is emitted.
                # The canonical hierarchy is the primary, single stored
                # copy of current capture, logs, filelists and run reports.
                entry['canonical_url']=(relative/'report.html').as_posix()
            if protocol_data:
                protocol_run=protocol_data.get('run',{})
                protocol_sha=protocol_run.get('commit')
                if (protocol_sha not in (verified_shas | {run['head_sha']})
                    or protocol_run.get('dirty') is not False
                    or str(protocol_run.get('workflow_run_id'))!=str(run['id'])
                    or str(protocol_run.get('workflow_attempt'))!=str(run.get('run_attempt',1))):
                    raise ValueError('protocol report provenance differs from clean CI run')
                if protocol_data.get('schema_version')!=1:
                    raise ValueError('unsupported protocol publication schema')
                entry['source_sha']=protocol_sha
                link_catalog = protocol_link_catalog(protocol_data)
                if link_catalog:
                    entry['protocol_links'] = link_catalog
                # Do not publish artifact-supplied HTML. Re-render the trusted
                # JSON through the site source's audited escaping/textContent UI.
                render_protocol_report(protocol_data, destination/'protocols.html')
            if variant_view is not None:
                page=render_variant_html(variant_view,variant_graph)
                (destination/'variant-architecture.html').write_text(
                    shell('Selected variant connectivity',page,
                          relative/'variant-architecture.html',repository,run['head_sha']))
            if trace:
                tested_sha=trace['run'].get('commit')
                if (tested_sha not in (verified_shas | {run['head_sha']})
                    or trace['run'].get('dirty') is not False
                    or str(trace['run'].get('workflow_run_id'))!=str(run['id'])
                    or str(trace['run'].get('workflow_attempt'))!=str(run.get('run_attempt',1))):
                    raise ValueError('AXI report provenance differs from its clean CI workflow run')
                # Show the actual source tested by the PR merge build, not the
                # branch head supplied by the GitHub Actions run metadata.
                entry['source_sha']=tested_sha
                # The collector validated both authentic Git trees before
                # recording this equality; the publisher never trusts a
                # shared PR branch name as evidence of source equivalence.
                matches=source.get('verified_equivalent_site_shas') or {}
                if (run.get('merged_pr') and
                        matches.get(tested_sha) and
                        re.fullmatch(r'[a-f0-9]{40}',matches[tested_sha])):
                    entry['verified_site_source_sha']=matches[tested_sha]
                # Only the trusted collector sets this attestation using
                # the checked-in hardware/DV execution-input fingerprint.
                fabric_matches=source.get('verified_equivalent_fabric_shas') or {}
                if (fabric_matches.get(tested_sha)
                        and re.fullmatch(r'[a-f0-9]{40}',fabric_matches[tested_sha])):
                    entry['verified_fabric_source_sha']=fabric_matches[tested_sha]
                if mr_view is not None:
                    trace['sections']['ddr_mrs']=mr_view
                render_report(trace,destination/'report.html')
                if memory_view is not None:
                    from scenario_memory_trace import embed_in_run_report
                    embed_in_run_report(destination/'report.html',memory_view)
                html=(destination/'report.html').read_text()
                up=os.path.relpath(output,destination).replace(os.sep,'/')
                nav=f'<p style="margin:0 0 12px"><a href="{up}/index.html">Verification hub</a> · <a href="{up}/runs.html">All runs</a> · <a href="{escape(run["html_url"])}">CI evidence</a></p>'
                nav+='<details><summary>Original evidence: raw events, transactions, logs, plan and filelists</summary><ul>'
                nav+=''.join(f'<li><a href="{escape(name)}">{escape(name)}</a></li>' for name in sorted(assets))+'</ul></details>'
                if protocol_data:
                    # The canonical per-test landing page contains a visible
                    # read-only protocol viewer for *all* observed sources,
                    # not just a link or the AXI-only transaction table.
                    # Protocols HTML is always re-rendered from trusted JSON.
                    nav+=('<section class="card" id="all-protocol-traffic" '
                          'aria-label="All captured protocol traffic">'
                          '<h2>All captured protocol traffic</h2>'
                          '<p>Same test and CI attempt: Ethernet, PCIe, DFI, '
                          'AXI, APB and future monitor records, where present. '
                          'This is the independently verified protocol capture, '
                          'not a synthetic combined trace.</p>'
                          '<p><a href="protocols.html">Open full protocol explorer</a>'
                          ' · <a href="protocol-transactions.json">Raw protocol JSON</a></p>'
                          '<iframe src="protocols.html" loading="lazy" '
                          'title="Source-verified per-test protocol observations" '
                          'style="display:block;width:100%;height:640px;'
                          'border:1px solid var(--line);border-radius:8px">'
                          '</iframe></section>')
                nav+=('<p><strong>Selected plan:</strong> '+escape(snapshot_status)
                      +(' · SHA-256 <code>'+escape(declared_hash[:16])+'</code>'
                        +' · <a href="planned-flow.json">Archived pre-run plan</a>'
                        if declared_hash else
                        ' · no original pre-run snapshot in this historical archive')
                      +'</p>')
                if variant_view is not None:
                    nav+=('<p><a href="variant-architecture.html">Selected variant 2D NoC/initiator/monitor diagram</a> '
                          '(generated source only; open accepted traffic below for runtime proof)</p>')
                if flow_data:
                    nav+='<p><a href="test-flow.html">INIT/RUN/CHECK verified steps</a></p>'
                (destination/'report.html').write_text(html.replace('<main>','<main>'+nav,1))
                transactions=trace['sections']['axi']['transactions']
                entry['observations']=len(transactions)
                entry['expected_errors']=sum(r.get('error_intent')=='expected' and r['role']=='initiator' for r in transactions)
                entry['undeclared_errors']=sum(r.get('error_intent')=='undeclared' and r['role']=='initiator' for r in transactions)
                entry['annotations']=trace['run'].get('annotations_available',False)
            else:
                if protocol_data and (destination/'protocols.html').is_file():
                    (destination/'report.html').write_text((destination/'protocols.html').read_text())
                    html=(destination/'report.html').read_text()
                    if '<main>' in html:
                        (destination/'report.html').write_text(
                            html.replace('<main>','<main>'+(
                                '<p><strong>Canonical run:</strong> <code>'+escape(canonical_path(selected_identity).as_posix())+
                                '</code> · <a href="identity.json">Immutable identity</a></p>'
                                if selected_identity else '')+render_intended_flow(intended),1))
                    entries.append(entry)
                    continue
                body='<p>This scope publishes its actual result, plan, filelist and logs. It has no AXI traffic observer.</p>'
                body+=f'<p><strong>Regression {"PASS" if entry["passed"] else "FAIL"}</strong> · {escape(entry["engine"])} · tested SHA <code>{escape(entry["source_sha"])}</code></p>'
                if entry['expected_failure']:body+='<p>Expected-failure case: '+escape(entry['expected_failure'])+'</p>'
                body+='<pre>'+escape(json.dumps(result,indent=2))+'</pre>'
                body+='<ul>'+''.join(f'<li><a href="{escape(name)}">{escape(name)}</a></li>' for name in assets)+'</ul>'
                (destination/'report.html').write_text(shell(target,body,relative/'report.html',repository,run['head_sha']))
            # Original report now has a definition-only flow independently of
            # the optional validated test-flow evidence overlay.
            report_html=destination/'report.html'
            if report_html.is_file():
                html=report_html.read_text()
                if '<main>' in html:
                    catalog=(runtime_selected.get('actor_monitor_catalog',{})
                             if runtime_selected else {})
                    declared=catalog.get('monitors',{})
                    source_count=declared.get('count')
                    initiators=declared.get('declared_initiators',[])
                    actor_note=(
                        '<p>Selected source monitor catalog: '+escape(str(source_count))+
                        ' boundaries, '+escape(str(len(initiators)))+
                        ' declared initiators · '+escape(declared.get('status','not_declared'))+
                        '. These are NOT proof of elaborated pins or accepted AXI traffic.</p>'
                        if source_count is not None else
                        '<p>Selected actor/monitor catalog unavailable for this run.</p>')
                    note=(
                        '<p>Selected per-run snapshot '+escape(runtime_selected['plan_sha256'][:16])+
                        ' · adapter '+escape(runtime_selected['adapter'])+
                        ' · internal steps independently instrumented only where available.</p>'+actor_note
                        if runtime_selected else
                        '<p>Historical run: command dispatch snapshot unavailable; '
                        'no unobserved actions implied.</p>')
                    if selected_identity is not None:
                        note+=('<p><strong>Canonical run:</strong> <code>'+
                               escape(canonical_path(selected_identity).as_posix())+
                               '</code> · <a href="identity.json">Immutable identity</a>. '
                               'Legacy report URL retained for historical compatibility.</p>')
                    report_html.write_text(html.replace('<main>','<main>'+note+render_intended_flow(intended),1))
            entries.append(entry)
    runs.sort(key=lambda r:r['created_at'],reverse=True)
    entries.sort(key=lambda r:r['recorded_at'],reverse=True)
    return runs,entries,notes


def shell(title,body,relative,repository,sha):
    prefix=os.path.relpath('.',str(Path(relative).parent)).replace(os.sep,'/')
    if prefix=='.':prefix=''
    else:prefix+='/'
    template=(ROOT/'tools/templates/site.html').read_text()
    navigation=''.join(f'<a href="{prefix}{path}">{label}</a>' for path,label in
                       [('index.html','Overview'),('topology.html','Topology'),('explorer.html','Chip architecture'),('fabric.html','Fabric Explorer'),('address-map.html','Address Map'),('runs.html','Test runs'),('docs.html','Documentation'),('reference.html','Source data')])
    return (template.replace('__TITLE__',escape(title)).replace('__NAV__',navigation).replace('__HOME__',prefix+'index.html')
            .replace('__CONTENT__',body).replace('__SOURCE__',escape(sha[:12]))
            .replace('__REPO__',f'https://github.com/{repository}/tree/{sha}'))


def markdown_pages(output,repository,sha):
    files=[ROOT/'README.md',ROOT/'AGENTS.md',*sorted((ROOT/'docs').glob('*.md')),ROOT/'gen/README.md']
    mapping={p.resolve():Path('readme.html') if p.name=='README.md' and p.parent==ROOT else p.relative_to(ROOT).with_suffix('.html') for p in files}
    listing=[]
    for source,relative in mapping.items():
        parser=MarkdownIt('commonmark',{'html':False}).enable(['table','strikethrough'])
        tokens=parser.parse(re.sub(r'<!--.*?-->','',source.read_text(),flags=re.S))
        seen={}
        for i,token in enumerate(tokens):
            if token.type=='heading_open':
                slug=re.sub(r'[^\w\- ]','',tokens[i+1].content.lower()).strip().replace(' ','-')
                count=seen.get(slug,0);seen[slug]=count+1
                token.attrSet('id',slug+(f'-{count}' if count else ''))
        def rewrite(items):
            for token in items:
                for attribute in ('href','src'):
                    value=token.attrGet(attribute)
                    if not value or value.startswith(('#','https:','http:','mailto:')):continue
                    url=urllib.parse.urlsplit(value)
                    target=(source.parent/urllib.parse.unquote(url.path)).resolve()
                    if not target.is_relative_to(ROOT):continue
                    if target in mapping:destination=mapping[target]
                    elif target.is_file() and (target.is_relative_to(ROOT/'gen') or target.is_relative_to(ROOT/'config') or target.name in ('Bender.yml','Bender.lock')):
                        destination=target.relative_to(ROOT)
                    elif target.is_dir() and target.is_relative_to(ROOT/'gen'):destination=Path('reference.html')
                    else:
                        kind='tree' if target.is_dir() else 'blob'
                        token.attrSet(attribute,f'https://github.com/{repository}/{kind}/{sha}/{target.relative_to(ROOT).as_posix()}'+('#'+url.fragment if url.fragment else ''))
                        continue
                    href=os.path.relpath(destination,relative.parent).replace(os.sep,'/')
                    token.attrSet(attribute,href+('#'+url.fragment if url.fragment else ''))
                if token.children:rewrite(token.children)
        rewrite(tokens)
        title=next((tokens[i+1].content for i,t in enumerate(tokens) if t.type=='heading_open'),'Documentation')
        content=parser.renderer.render(tokens,parser.options,{})
        destination=output/relative;destination.parent.mkdir(parents=True,exist_ok=True)
        destination.write_text(shell(title,'<article class="prose">'+content+'</article>',relative,repository,sha))
        listing.append({'title':title,'path':relative.as_posix()})
    return listing


def ddr_mr_views(entries, output):
    """Source-proven per-test DRAM MR writes; never infer from a CSR map.

    A previous successful run must retain both its exact evidence file and
    passive DFI protocol capture. Missing/old artifacts stay unavailable.
    """
    from ddr_mr_report import read_evidence
    views=[]
    for item in entries:
        if (item.get('target') not in ('chip-ddr4-real','chip-ethernet-ddr-pcie')
                or item.get('passed') is not True or not item.get('axi')):
            continue
        folder=output/Path(item['path']).parent
        raw=folder/'ddr4_mrs_evidence.json'
        protocol=folder/'protocol-transactions.json'
        if not raw.is_file() or not protocol.is_file():
            continue
        evidence=read_evidence(raw,protocol)
        views.append({
            'label': item['target']+' · CI '+str(item['run_id']),
            'target':item['target'],
            'run_id':item['run_id'],
            'source_sha':item['source_sha'],
            'report_href':item['path'],
            'evidence_href':(Path(item['path']).parent/'ddr4_mrs_evidence.json').as_posix(),
            'evidence':evidence,
        })
    return views[:16]


def ddr_csr_views(entries, output):
    """Only source-verified, successful DDR run JSON can supply DDR CSR rows.

    Existing evidence_index() already rejects PR artifacts without verified
    original run+commit provenance. Do not treat an opt-in controller's CSR
    catalog as registers present in the default AXI-RAM chip.
    """
    views = []
    for item in entries:
        if item.get('target') != 'chip-ddr4-real' or not item.get('passed') or not item.get('axi'):
            continue
        path = output / Path(item['path']).parent / 'axi-transactions.json'
        if not path.is_file():
            continue
        data = json.loads(path.read_text())
        model = data.get('sections', {}).get('address_map', {})
        if model.get('variant') != 'ddr_real' or model.get('schema_version') != 1:
            continue
        regions = [r for r in model.get('regions', []) if r.get('name') == 'memory0.ctrl']
        if (len(regions) != 1 or regions[0].get('size') != '0x4000'
                or regions[0].get('base') != '0x40030000'
                or not regions[0].get('registers')
                or not all(r.get('definition_status') ==
                           'native_LiteDRAM_generated_CSR_not_bus_coverage'
                           for r in regions[0]['registers'])):
            continue
        views.append({
            'label': f"Real LiteDRAM · {item['target']} · {item['run_id']}",
            'source_sha': item['source_sha'],
            'run_id': item['run_id'],
            'report_href': item['path'],
            'catalog': model,
        })
    return views[:12]


def build(output,evidence,repository,sha,config):
    if output.exists():
        if not (output/'.soc-site').is_file():raise ValueError('refusing to replace an unowned site directory')
        shutil.rmtree(output)
    output.mkdir(parents=True);(output/'.soc-site').write_text('v1\n');(output/'.nojekyll').touch()
    for name in ('gen','config'):shutil.copytree(ROOT/name,output/name)
    for name in ('Bender.yml','Bender.lock'):shutil.copyfile(ROOT/name,output/name)
    docs=markdown_pages(output,repository,sha)
    runs,entries,notes=evidence_index(evidence,output,repository)
    import fabric_report
    fabric = fabric_report.load(ROOT)
    catalog=yaml.safe_load((ROOT/'config/regression.yaml').read_text())
    source_scenario=json.loads((ROOT/'config/scenarios/cpu-bfm-ddr-roundtrip.json').read_text())
    flow_intents=intended_flow_catalog(catalog,scenario=source_scenario)
    noc=json.loads((ROOT/'gen/noc/floonoc/manifest.json').read_text())
    chip=json.loads((ROOT/'gen/chip/manifest.json').read_text())
    monitors=json.loads((ROOT/'gen/supernoc/axi_monitors.json').read_text())
    fabric_report.attach_one_beat_observations(fabric, entries, output, sha)
    coverage=fabric['latency_table']['evidence_coverage']
    print("FABRIC COVERAGE: " + json.dumps({
        'source_sha':sha,'status':coverage['status'],
        'measured_routes':coverage['current_measured_routes'],
        'historical_observations':coverage['historical_observations']},
        sort_keys=True),flush=True)
    dump(output/'data/fabric.json',fabric)
    # Config is authoritative for addresses. Optional pinned RDL output adds
    # register definitions, but never asserts active RTL or observed traffic.
    import address_map
    csr_path=ROOT/'.tools/csr-verified/csr-map.json'
    csr_ready=csr_path.is_file()
    address_catalog=address_map.build(ROOT/'config/soc.yaml',
        csr_path=csr_path if csr_ready else None,
        variant='cold_boot' if csr_ready else 'architecture')
    # All config IPs are discovered from SoC composition. C/RTL crosschecked
    # register references are a distinct layer from actually qualified CSRs.
    # Unknown future subsystem/CSR sources fail CI unless explicitly explained.
    from csr_source_references import attach_sources
    source_coverage=attach_sources(address_catalog)
    dump(output/'data/csr-source-coverage.json',source_coverage)
    dump(output/'data/soc-address-map.json',address_catalog)
    dump(output/'data/test-intents.json',flow_intents)
    ddr_views = ddr_csr_views(entries, output)
    dump(output/'data/ddr-csr-verified-runs.json', ddr_views)
    from ddr_mr_report import layout as mr_layout
    mr_catalog=mr_layout(ROOT/'csr/rdl/ddr4_mode_registers.rdl')
    dump(output/'data/ddr4-mr-definitions.json', mr_catalog)
    ddr_mr_evidence=ddr_mr_views(entries, output)
    dump(output/'data/ddr4-mr-verified-runs.json', ddr_mr_evidence)
    (output/'data/soc-data-memories.rdl').write_text(address_map.memory_rdl_view(address_catalog))
    if csr_ready:
        for filename in ('csr-map.json','soc_csr_bases.h','soc_boot_reset_ctrl_regs.h','boot_reset_ctrl_types.h'):
            file=csr_path.parent/filename
            if not file.is_file():
                raise ValueError('incomplete PeakRDL catalog: '+filename)
            shutil.copyfile(file,output/'data'/filename)
        # Publish the header consumed by production DMA C firmware, with
        # byte-for-byte SystemRDL source validation. This is not MMIO proof.
        from csr_dma_headers import extract as dma_extract, header as dma_header
        dma_source=ROOT/'sw/dma/generated/soc_dma_shim_regs.h'
        if not dma_source.is_file() or dma_source.read_text()!=dma_header(dma_extract()):
            raise ValueError('production DMA CSR header missing or differs from SystemRDL')
        shutil.copyfile(dma_source,output/'data/soc_dma_shim_regs.h')
    from design_explorer import catalog as design_catalog
    design_graph = design_catalog(ROOT)
    dump(output/'data/design-graph.json', design_graph)
    from signal_inventory import build as signal_inventory_build
    signal_inventory = signal_inventory_build(ROOT)
    dump(output/'data/signal-inventory.json', signal_inventory)
    # Optional compiler-parsed *actual* RTL instance/port evidence. The
    # source fingerprints prevent stale output from another generated chip
    # from being presented as current. Local docs previews can omit this.
    rtl_source=ROOT/'.tools/rtl-architecture.json'
    parsed_rtl={"schema_version":1,"producer":"slang",
                "evidence":"compiler_parse_not_run",
                "modules":[],"fabric_contract":{},
                "summary":{"modules":0,"instances":0,"noc_instances":0}}
    if rtl_source.is_file():
        candidate=json.loads(rtl_source.read_text())
        if candidate.get("producer")!="slang" or candidate.get("schema_version")!=1:
            raise ValueError("invalid parsed RTL architecture schema")
        for rel,digest in candidate.get("source_sha256",{}).items():
            expected=hashlib.sha256((ROOT/rel).read_bytes()).hexdigest()
            if expected!=digest:
                raise ValueError("stale slang RTL architecture: "+rel)
        if not candidate.get("fabric_contract",{}).get("independent_planes"):
            raise ValueError("parsed RTL failed independent data/config fabric contract")
        parsed_rtl=candidate
    dump(output/'data/rtl-architecture.json', parsed_rtl)
    # Index *actual parsed root instances* for every generic diagram
    # boundary. Ambiguous or missing mappings remain explicitly unresolved;
    # a source name match is never treated as selected-variant elaboration.
    from rtl_instance_bindings import resolve as resolve_rtl_instance_bindings
    rtl_bindings=resolve_rtl_instance_bindings(
        design_graph, parsed_rtl, top=chip['top'])
    dump(output/'data/rtl-instance-bindings.json', rtl_bindings)
    dataset={'schema_version':1,'title':config['title'],'source_sha':sha,'repository':repository,
             'production_dma_header_sha256':(hashlib.sha256(
                 (output/'data/soc_dma_shim_regs.h').read_bytes()).hexdigest() if csr_ready else None),
             'built_at':datetime.now(timezone.utc).isoformat(),'runs':runs,'entries':entries,
             'notes':notes,'documents':docs,'networks':noc['networks'],'chip':chip,
             'monitors':monitors['monitors'],'fabric':fabric['summary'],'tests':catalog['tests'],
             'test_intents':flow_intents}
    dump(output/'data/site.json',dataset)
    data=json.dumps(dataset,separators=(',',':')).replace('<','\\u003c')
    for page in ('index','topology','explorer','fabric','address-map','runs','docs','reference'):
        body=(ROOT/('tools/templates/site_'+page+'.html')).read_text().replace('__SITE_DATA__',data)
        if page=='explorer':
            graph_data = json.dumps(design_graph, separators=(',', ':')).replace('<','\\u003c')
            body = body.replace('__GRAPH_DATA__',graph_data)
            signal_data = json.dumps(signal_inventory, separators=(',', ':')).replace('<','\\u003c')
            body = body.replace('__SIGNAL_DATA__', signal_data)
            parsed_data = json.dumps(parsed_rtl, separators=(',', ':')).replace('<','\\u003c')
            body = body.replace('__RTL_PARSE_DATA__', parsed_data)
            bindings_data = json.dumps(rtl_bindings, separators=(',', ':')).replace('<','\\u003c')
            body = body.replace('__RTL_INSTANCE_BINDINGS__', bindings_data)
            # Every protocol monitor with verified evidence is discoverable:
            # source ID, protocol and role come from the audited VIP capture,
            # not manually registered workflow names or guessed hardware.
            link_runs = [
                {'run_id': e['run_id'], 'attempt': e['attempt'],
                 'target': e['target'], 'recorded_at': e['recorded_at'],
                 'source_sha': e['source_sha'], 'passed': e['passed'],
                 'workflow': e['workflow'],
                 'report_path': e['path'].rsplit('/',1)[0] + '/protocols.html',
                 'axi_report_path': e['path'],
                 'raw_path': e['path'].rsplit('/',1)[0] + '/protocol-transactions.json',
                 'links': e['protocol_links']}
                for e in entries if e.get('protocol_links')
            ]
            protocol_links_json=json.dumps(link_runs,separators=(',',':')).replace('<','\\u003c')
            body=body.replace('__PROTOCOL_LINK_DATA__',protocol_links_json)
            architecture_js = (ROOT/'tools/templates/site_arch_explorer.js').read_text()
            body = body.replace('__ARCH_JS__', architecture_js)
        if page=='address-map':
            map_json=json.dumps(address_catalog,separators=(',',':')).replace('<','\\u003c')
            body=body.replace('__ADDRESS_MAP_DATA__',map_json)
            ddr_json = json.dumps(ddr_views,separators=(',',':')).replace('<','\\u003c')
            body=body.replace('__DDR_CSR_VARIANTS__',ddr_json)
            mr_json=json.dumps(mr_catalog,separators=(',',':')).replace('<','\\u003c')
            body=body.replace('__DDR_MR_CATALOG__',mr_json)
            mr_views_json=json.dumps(ddr_mr_evidence,separators=(',',':')).replace('<','\\u003c')
            body=body.replace('__DDR_MR_RUNS__',mr_views_json)
            details=('<a href="data/csr-map.json">Generated CSR metadata</a> · '
                     '<a href="data/soc_boot_reset_ctrl_regs.h">Reset CSR C header</a> · '
                     '<a href="data/soc_dma_shim_regs.h">Production DMA CSR C header</a> · '
                     '<a href="data/soc_csr_bases.h">Instance-base C header</a>') if csr_ready else (
                     'RDL register details unavailable in this local preview')
            body=body.replace('__CSR_SOURCE_LINKS__',details)
        if page=='reference':
            body=body.replace('__CSR_SOURCE_LINKS__',
                '<li><a href="data/csr-map.json">Generated CSR metadata</a></li>'
                '<li><a href="data/soc_dma_shim_regs.h">Production DMA CSR C header</a></li>'
                if csr_ready else '')
        if page=='runs':
            # Trusted static JavaScript, not CI-supplied executable HTML.
            traffic_js=(ROOT/'tools/templates/site_runs_traffic.js').read_text()
            body=body.replace('__RUN_TRAFFIC_JS__',traffic_js)
        if page=='fabric':
            fabric_data=json.dumps(fabric,separators=(',',':')).replace('<','\\u003c')
            body=body.replace('__FABRIC_DATA__',fabric_data)
        (output/(page+'.html')).write_text(shell(config['title'],body,Path(page+'.html'),repository,sha))
    return dataset


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,default=ROOT/'.tools/pages-site')
    parser.add_argument('--evidence',type=Path,default=ROOT/'.tools/pages-evidence')
    parser.add_argument('--repository',default=os.environ.get('GITHUB_REPOSITORY','r987r/xezim-hello-world'))
    parser.add_argument('--collect',action='store_true')
    parser.add_argument('--ensure-pages',action='store_true')
    args=parser.parse_args()
    client=GitHub(args.repository,os.environ.get('GH_TOKEN') or os.environ.get('GITHUB_TOKEN'))
    if args.ensure_pages:
        site=client.pages();print('PAGES_URL='+site['html_url']);return
    config=yaml.safe_load((ROOT/'config/publication.yaml').read_text())
    if config['schema_version']!=1:raise ValueError('unsupported publication schema')
    if args.collect:collect(client,config,args.evidence)
    sha=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip()
    result=build(args.output,args.evidence,args.repository,sha,config)
    print(f'Built {len(result["documents"])} docs, {len(result["runs"])} CI runs, {len(result["entries"])} test-result pages at {args.output}')


if __name__=='__main__':main()
