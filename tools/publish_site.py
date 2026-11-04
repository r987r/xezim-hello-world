#!/usr/bin/env python3
"""Build the static GitHub Pages hub from repo sources and actual CI artifacts.

Evidence always retains its own workflow run, attempt and tested commit.
The builder never treats an older green run as current-source validation.
"""
import argparse
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

ROOT=Path(__file__).resolve().parents[1]
FILES={'result.json','plan.json','sources.f','simulation.log','build.log','results.xml',
       'axi-transactions.json','axi-events.jsonl'}


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


def collect(client,config,destination):
    destination.mkdir(parents=True,exist_ok=True)
    selected={w['file']:[] for w in config['workflows']}
    # Limit API history as well as output size. Only trusted main runs are
    # ingested; PR artifacts and PR code are never deployed by workflow_run.
    for page in range(1,6):
        response=client.request(f'/repos/{client.repository}/actions/runs?branch=main&per_page=100&page={page}')
        batch=response['workflow_runs']
        for run in batch:
            file=run['path'].split('/')[-1]
            if file in selected and run['head_branch']=='main' and len(selected[file])<config['history_per_workflow']:
                selected[file].append(run)
        if not batch or all(len(r)>=config['history_per_workflow'] for r in selected.values()):
            break
    notes=[]
    for workflow in config['workflows']:
        for run in selected[workflow['file']]:
            folder=destination/(str(run['id'])+'-'+str(run.get('run_attempt',1)))
            folder.mkdir(parents=True,exist_ok=True)
            dump(folder/'run.json',run)
            dump(folder/'workflow.json',workflow)
            if run['status']!='completed':continue
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
                dump(folder/('artifact-'+str(artifact['id'])+'.json'),artifact)
    dump(destination/'collection.json',{'notes':notes})


def evidence_index(evidence,output,repository):
    runs,entries,notes=[],[],[]
    if (evidence/'collection.json').exists():notes=json.loads((evidence/'collection.json').read_text()).get('notes',[])
    for file in sorted(evidence.glob('*/run.json')):
        source=json.loads(file.read_text())
        workflow=json.loads((file.parent/'workflow.json').read_text())
        run={k:source.get(k) for k in ('id','name','status','conclusion','head_sha','head_branch','run_attempt','html_url','created_at','updated_at','path')}
        run['label']=workflow['label']
        runs.append(run)
        if run['head_branch']!='main':raise ValueError('publication cache contains a non-main run')
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
            entry={'target':target,'engine':plan.get('engine','unknown'),'passed':result.get('passed') is True,
                   'expected_failure':plan.get('expect_failure'),'stage':result.get('stage'),
                   'run_id':run['id'],'attempt':run.get('run_attempt',1),'source_sha':run['head_sha'],
                   'recorded_at':run['created_at'],'workflow':run['label'],'workflow_url':run['html_url'],
                   'path':str(relative/'report.html'),'assets':sorted(assets),
                   'axi':trace is not None,'result':result}
            if trace:
                if (trace['run'].get('commit')!=run['head_sha'] or trace['run'].get('dirty') is not False
                    or str(trace['run'].get('workflow_run_id'))!=str(run['id'])
                    or str(trace['run'].get('workflow_attempt'))!=str(run.get('run_attempt',1))):
                    raise ValueError('AXI report provenance differs from its clean CI workflow run')
                render_report(trace,destination/'report.html')
                html=(destination/'report.html').read_text()
                up=os.path.relpath(output,destination).replace(os.sep,'/')
                nav=f'<p style="margin:0 0 12px"><a href="{up}/index.html">Verification hub</a> · <a href="{up}/runs.html">All runs</a> · <a href="{escape(run["html_url"])}">CI evidence</a></p>'
                nav+='<details><summary>Original evidence: raw events, transactions, logs, plan and filelists</summary><ul>'
                nav+=''.join(f'<li><a href="{escape(name)}">{escape(name)}</a></li>' for name in sorted(assets))+'</ul></details>'
                (destination/'report.html').write_text(html.replace('<main>','<main>'+nav,1))
                transactions=trace['sections']['axi']['transactions']
                entry['observations']=len(transactions)
                entry['expected_errors']=sum(r.get('error_intent')=='expected' and r['role']=='initiator' for r in transactions)
                entry['undeclared_errors']=sum(r.get('error_intent')=='undeclared' and r['role']=='initiator' for r in transactions)
                entry['annotations']=trace['run'].get('annotations_available',False)
            else:
                body='<p>This scope publishes its actual result, plan, filelist and logs. It has no AXI traffic observer.</p>'
                body+=f'<p><strong>Regression {"PASS" if entry["passed"] else "FAIL"}</strong> · {escape(entry["engine"])} · tested SHA <code>{escape(run["head_sha"])}</code></p>'
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
                       [('index.html','Overview'),('topology.html','Topology'),('fabric.html','Fabric Explorer'),('runs.html','Test runs'),('docs.html','Documentation'),('reference.html','Source data')])
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
    dataset={'schema_version':1,'title':config['title'],'source_sha':sha,'repository':repository,
             'built_at':datetime.now(timezone.utc).isoformat(),'runs':runs,'entries':entries,
             'notes':notes,'documents':docs,'networks':noc['networks'],'chip':chip,
             'monitors':monitors['monitors'],'fabric':fabric['summary'],'tests':catalog['tests']}
    dump(output/'data/site.json',dataset)
    data=json.dumps(dataset,separators=(',',':')).replace('<','\\u003c')
    for page in ('index','topology','fabric','runs','docs','reference'):
        body=(ROOT/('tools/templates/site_'+page+'.html')).read_text().replace('__SITE_DATA__',data)
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
