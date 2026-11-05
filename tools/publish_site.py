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

ROOT=Path(__file__).resolve().parents[1]
FILES={'result.json','plan.json','sources.f','simulation.log','build.log','results.xml',
       'axi-transactions.json','axi-events.jsonl',
       'protocol-transactions.json','protocol-events.jsonl','memory-operations.json'}


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
        with self.opener.open(req,timeout=60) as response:
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


def extract_archive(data,destination,config,digest=None):
    if len(data)>config['max_archive_mib']*1024**2:
        raise ValueError('CI archive exceeds publication size limit')
    if digest and digest.startswith('sha256:') and hashlib.sha256(data).hexdigest()!=digest[7:]:
        raise ValueError('CI archive digest mismatch')
    import io
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        if sum(i.file_size for i in archive.infolist())>config['max_expanded_mib']*1024**2:
            raise ValueError('expanded CI archive exceeds publication size limit')
        for info in archive.infolist():
            path=PurePosixPath(info.filename)
            mode=info.external_attr>>16
            if path.is_absolute() or '..' in path.parts or '\\' in info.filename or stat.S_ISLNK(mode):
                raise ValueError('unsafe CI archive member')
        archive.extractall(destination)


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
    # Staged DDR4 generation/test *not* in the active Bender NoC or chip
    # simulation source lists. Future integration changes the included
    # Bender/config/generated RTL input hashes and invalidates old evidence.
    'rtl/memory/ddr4/',
)
FABRIC_EXCLUDED_FILES = {
    'README.md', 'AGENTS.md', 'tools/publish_site.py',
    'tools/fabric_report.py', 'tools/templates/site.html',
    'tools/templates/run_report.html',
    # Read-only architecture extraction and diagram rendering have no
    # simulator or AXI monitor runtime side effects.
    'tools/rtl_instance_parser.py', 'tools/design_explorer.py',
    'tools/signal_inventory.py', 'tools/signal_paths.py',
    'tools/design_elaborate.py', 'tools/design_netlist.py',
    'tools/noc_diagrams.py', 'tools/diagram_svg.py', 'tools/diagram_gen.py',
}
# CI execution jobs (tool versions and invocation) must also be identical.
# Trigger/scheduling-only edits do not alter simulated timing and are ignored.
FABRIC_EXECUTION_WORKFLOWS = ('floonoc-elab.yml', 'full-chip.yml')
FABRIC_REQUIRED_INPUTS = frozenset({
    'config/soc.yaml', 'config/interface_contracts.yaml',
    'config/regression.yaml', 'config/ip.lock.yaml',
    'dv/supernoc/test_supernoc.py', 'dv/common/axi_trace.py',
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



def collect(client,config,destination):
    destination.mkdir(parents=True,exist_ok=True)
    selected={w['file']:[] for w in config['workflows']}
    merged_heads=merged_main_pr_heads(client)
    site_sha=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip()
    tree_cache={}
    fabric_cache={}
    # Only trusted main and source-SHA-matched merged PR workflow runs are
    # published. PR code and artifacts are not executed in this trusted job.
    for page in range(1,6):
        response=client.request(f'/repos/{client.repository}/actions/runs?per_page=100&page={page}')
        batch=response['workflow_runs']
        for run in batch:
            file=run['path'].split('/')[-1]
            if file not in selected or len(selected[file])>=config['history_per_workflow']:
                continue
            merged_pr=verified_merged_pr(run,merged_heads)
            if run.get('head_branch')!='main' and merged_pr is None:
                continue
            run=dict(run)
            if merged_pr is not None:
                run['verified_merged_pr']=merged_pr
            selected[file].append(run)
        if not batch or all(len(r)>=config['history_per_workflow'] for r in selected.values()):
            break
    notes=[]
    verified_cache={}
    for workflow in config['workflows']:
        for run in selected[workflow['file']]:
            folder=destination/(str(run['id'])+'-'+str(run.get('run_attempt',1)))
            folder.mkdir(parents=True,exist_ok=True)
            dump(folder/'workflow.json',workflow)
            if run['status']!='completed':
                dump(folder/'run.json',run)
                continue
            artifacts=client.request(f'/repos/{client.repository}/actions/runs/{run["id"]}/artifacts?per_page=100')['artifacts']
            for artifact in artifacts:
                if artifact['name'] not in workflow['artifacts']:continue
                if artifact['expired']:
                    notes.append(f'Run {run["id"]}: expired artifact {artifact["name"]}')
                    continue
                target=folder/('artifact-'+str(artifact['id']))
                if not (target/'.complete').exists():
                    raw=client.request(f'/repos/{client.repository}/actions/artifacts/{artifact["id"]}/zip',binary=True)
                    target.mkdir(exist_ok=True)
                    extract_archive(raw,target,config,artifact.get('digest'))
                    (target/'.complete').write_text('verified\n')
                if run.get('verified_merged_pr') is not None:
                    verified=set(run.get('verified_tested_shas',[]))
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
            if (not re.fullmatch(r'[a-z][a-z0-9-]*',target) or
                target!=result_path.parent.name and not re.fullmatch(r'artifact-[0-9]+',result_path.parent.name)):
                raise ValueError('invalid target in CI result artifact')
            if target in found:raise ValueError('duplicate target evidence in one workflow run')
            found.add(target)
            source_dir=result_path.parent
            plan=json.loads((source_dir/'plan.json').read_text()) if (source_dir/'plan.json').exists() else {}
            relative=Path('runs')/(str(run['id'])+'-'+str(run.get('run_attempt',1)))/target
            destination=output/relative;destination.mkdir(parents=True,exist_ok=True)
            assets=[]
            for item in source_dir.iterdir():
                if item.is_file() and (item.name in FILES or item.suffix in ('.log','.f')):
                    shutil.copyfile(item,destination/item.name);assets.append(item.name)
            trace_path=source_dir/'axi-transactions.json'
            trace=json.loads(trace_path.read_text()) if trace_path.exists() else None
            protocol_path=source_dir/'protocol-transactions.json'
            protocol_data=json.loads(protocol_path.read_text()) if protocol_path.exists() else None
            entry={'target':target,'engine':plan.get('engine','unknown'),'passed':result.get('passed') is True,
                   'expected_failure':plan.get('expect_failure'),'stage':result.get('stage'),
                   'run_id':run['id'],'attempt':run.get('run_attempt',1),'source_sha':run['tested_sha'],
                   'pr_head_sha':run['head_sha'],'merged_pr':run.get('merged_pr'),
                   'recorded_at':run['created_at'],'workflow':run['label'],'workflow_url':run['html_url'],
                   'path':str(relative/'report.html'),'assets':sorted(assets),
                   'axi':trace is not None,
                   'protocols':sorted({r['protocol'] for r in protocol_data.get('records',[])}) if protocol_data else [],
                   'protocol_observations':len(protocol_data['records']) if protocol_data else 0,
                   'result':result}
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
                # Do not publish artifact-supplied HTML. Re-render the trusted
                # JSON through the site source's audited escaping/textContent UI.
                render_protocol_report(protocol_data, destination/'protocols.html')
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
                render_report(trace,destination/'report.html')
                html=(destination/'report.html').read_text()
                up=os.path.relpath(output,destination).replace(os.sep,'/')
                nav=f'<p style="margin:0 0 12px"><a href="{up}/index.html">Verification hub</a> · <a href="{up}/runs.html">All runs</a> · <a href="{escape(run["html_url"])}">CI evidence</a></p>'
                nav+='<details><summary>Original evidence: raw events, transactions, logs, plan and filelists</summary><ul>'
                nav+=''.join(f'<li><a href="{escape(name)}">{escape(name)}</a></li>' for name in sorted(assets))+'</ul></details>'
                if protocol_data:
                    nav+='<p><a href="protocols.html">Unified protocol explorer</a></p>'
                (destination/'report.html').write_text(html.replace('<main>','<main>'+nav,1))
                transactions=trace['sections']['axi']['transactions']
                entry['observations']=len(transactions)
                entry['expected_errors']=sum(r.get('error_intent')=='expected' and r['role']=='initiator' for r in transactions)
                entry['undeclared_errors']=sum(r.get('error_intent')=='undeclared' and r['role']=='initiator' for r in transactions)
                entry['annotations']=trace['run'].get('annotations_available',False)
            else:
                if protocol_data and (destination/'protocols.html').is_file():
                    (destination/'report.html').write_text((destination/'protocols.html').read_text())
                    entries.append(entry)
                    continue
                body='<p>This scope publishes its actual result, plan, filelist and logs. It has no AXI traffic observer.</p>'
                body+=f'<p><strong>Regression {"PASS" if entry["passed"] else "FAIL"}</strong> · {escape(entry["engine"])} · tested SHA <code>{escape(entry["source_sha"])}</code></p>'
                if entry['expected_failure']:body+='<p>Expected-failure case: '+escape(entry['expected_failure'])+'</p>'
                body+='<pre>'+escape(json.dumps(result,indent=2))+'</pre>'
                body+='<ul>'+''.join(f'<li><a href="{escape(name)}">{escape(name)}</a></li>' for name in assets)+'</ul>'
                (destination/'report.html').write_text(shell(target,body,relative/'report.html',repository,run['head_sha']))
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
                       [('index.html','Overview'),('topology.html','Topology'),('explorer.html','Chip architecture'),('fabric.html','Fabric Explorer'),('runs.html','Test runs'),('docs.html','Documentation'),('reference.html','Source data')])
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
    noc=json.loads((ROOT/'gen/noc/floonoc/manifest.json').read_text())
    chip=json.loads((ROOT/'gen/chip/manifest.json').read_text())
    monitors=json.loads((ROOT/'gen/supernoc/axi_monitors.json').read_text())
    fabric_report.attach_one_beat_observations(fabric, entries, output, sha)
    dump(output/'data/fabric.json',fabric)
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
    dataset={'schema_version':1,'title':config['title'],'source_sha':sha,'repository':repository,
             'built_at':datetime.now(timezone.utc).isoformat(),'runs':runs,'entries':entries,
             'notes':notes,'documents':docs,'networks':noc['networks'],'chip':chip,
             'monitors':monitors['monitors'],'fabric':fabric['summary'],'tests':catalog['tests']}
    dump(output/'data/site.json',dataset)
    data=json.dumps(dataset,separators=(',',':')).replace('<','\\u003c')
    for page in ('index','topology','explorer','fabric','runs','docs','reference'):
        body=(ROOT/('tools/templates/site_'+page+'.html')).read_text().replace('__SITE_DATA__',data)
        if page=='explorer':
            graph_data = json.dumps(design_graph, separators=(',', ':')).replace('<','\\u003c')
            body = body.replace('__GRAPH_DATA__',graph_data)
            signal_data = json.dumps(signal_inventory, separators=(',', ':')).replace('<','\\u003c')
            body = body.replace('__SIGNAL_DATA__', signal_data)
            parsed_data = json.dumps(parsed_rtl, separators=(',', ':')).replace('<','\\u003c')
            body = body.replace('__RTL_PARSE_DATA__', parsed_data)
            architecture_js = (ROOT/'tools/templates/site_arch_explorer.js').read_text()
            body = body.replace('__ARCH_JS__', architecture_js)
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
