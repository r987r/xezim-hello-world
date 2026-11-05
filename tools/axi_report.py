"""Turn passive AXI channel events into per-boundary transactions and HTML.

AXI IDs are scoped to a boundary/reset epoch. This is reporting glue, not
protocol VIP and not a global source-ID reconstruction through the NoCs.
"""
from collections import defaultdict, deque
import json
import os
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[1]
ORDER = {'reset':0, 'capture_start':1,'phase':1,'clock_period':1,'expect_response':1,
         'aw':2, 'ar':3, 'w':4, 'r':5, 'b':6}


def number(value):
    return int(value, 0) if isinstance(value, str) else int(value)


class Boundary:
    def __init__(self, entry, regions):
        self.entry, self.regions = entry, regions
        self.rows, self.issues = [], []
        self.epoch = 0
        self.clear()

    def clear(self):
        self.aw, self.wbursts = deque(), deque()
        self.wcurrent = []
        self.reads, self.writes = defaultdict(deque), defaultdict(deque)
        self.expectations = []

    def reset(self):
        for row in self.rows:
            if row['status'] == 'incomplete':
                row['status'] = 'reset_aborted'
        self.epoch += 1
        self.clear()

    def new(self, event, operation):
        f = event['fields']
        address = number(f['addr'])
        matches = [r['name'] for r in self.regions if r['plane'] == self.entry['plane']
                   and number(r['base']) <= address < number(r['base']) + number(r['size'])]
        row = {'uid':f'{self.entry["id"]}:{self.epoch}:{len(self.rows)}',
               'monitor':self.entry['id'], 'role':self.entry['role'],
               'plane':self.entry['plane'], 'network':self.entry['network'],
               'endpoints':self.entry['endpoints'], 'epoch':self.epoch,
               'operation':operation,'axi_id':f['id'],'address':f['addr'],
               'phase':event.get('phase'),
               'region':', '.join(matches) or 'unmapped', 'request':dict(f),
               'start_ps':event['time_ps'],'end_ps':None,'latency_ps':None,
               'expected_beats':number(f['len'])+1,'beats':[],
               'response':None,'status':'incomplete','issues':[]}
        expectation = next((e for e in self.expectations if e['operation']==operation
                            and number(e['address'])==address and e['time_ps']<=event['time_ps']),None)
        if expectation:
            self.expectations.remove(expectation)
            row['expected_response']=expectation['response']
            row['expected_reason']=expectation['reason']
        self.rows.append(row)
        return row

    def bind_writes(self):
        # AXI4 W has no ID: bursts bind to AW in accepted address order.
        # W is allowed to arrive before AW; preserve both queues.
        while self.aw and self.wbursts:
            row, beats = self.aw.popleft(), self.wbursts.popleft()
            row['beats'] = beats
            if len(beats) != row['expected_beats']:
                row['issues'].append('write beat count differs from AWLEN')

    def complete(self, row, event):
        row['end_ps'] = event['time_ps']
        row['latency_ps'] = event['time_ps'] - row['start_ps']
        row['status'] = 'complete'

    def consume(self, event):
        ch, f = event['channel'], event['fields']
        if ch in ('aw','ar'):
            row = self.new(event, 'write' if ch == 'aw' else 'read')
            (self.writes if ch == 'aw' else self.reads)[number(f['id'])].append(row)
            if ch == 'aw':
                self.aw.append(row)
                self.bind_writes()
        elif ch == 'w':
            self.wcurrent.append({**f,'time_ps':event['time_ps']})
            if number(f['last']):
                self.wbursts.append(self.wcurrent)
                self.wcurrent = []
                self.bind_writes()
        elif ch in ('b','r'):
            pending = (self.writes if ch == 'b' else self.reads)[number(f['id'])]
            if not pending:
                self.issues.append({'time_ps':event['time_ps'],'channel':ch,
                                    'id':f['id'],'message':'response without an accepted request in this reset epoch'})
                return
            row = pending[0]
            if ch == 'b':
                row['response'] = f.get('resp','0x0')
                if not row['beats']:
                    row['issues'].append('B arrived before a complete W burst')
                self.complete(row,event)
                pending.popleft()
            else:
                row['beats'].append({**f,'time_ps':event['time_ps']})
                row['response'] = hex(max(number(row['response'] or 0),number(f.get('resp',0))))
                if number(f['last']):
                    if len(row['beats']) != row['expected_beats']:
                        row['issues'].append('read beat count differs from ARLEN')
                    self.complete(row,event)
                    pending.popleft()

    def finish(self):
        if self.wcurrent and self.aw:
            self.aw[0]['beats'] = self.wcurrent
        if self.wbursts or (self.wcurrent and not self.aw):
            self.issues.append({'message':'unaddressed W data remains at capture end'})
        return self.rows


def correlate(events, catalog):
    states = {m['id']:Boundary(m,catalog['regions']) for m in catalog['monitors']}
    controls = []
    current_phase = None
    for event in sorted(events, key=lambda e:(e['time_ps'],ORDER.get(e['channel'],99))):
        ch = event['channel']
        if ch == 'reset':
            if event['active']:
                for state in states.values():
                    state.reset()
        elif ch in ('capture_start','capture_overflow','clock_period'):
            controls.append(event)
        elif ch == 'phase':
            current_phase = event['label']
            controls.append(event)
        elif ch == 'expect_response':
            if event['monitor'] not in states or states[event['monitor']].entry['role']!='initiator':
                raise ValueError('AXI expectations must name an initiator boundary')
            states[event['monitor']].expectations.append(event)
        elif ch in ('aw','w','b','ar','r'):
            if event['monitor'] not in states:
                raise ValueError('event for uncataloged AXI boundary: '+event['monitor'])
            if ch in ('aw','ar'):
                event = {**event, 'phase':current_phase}
            states[event['monitor']].consume(event)
        else:
            raise ValueError('unknown AXI event channel: '+ch)
    rows = sorted([r for s in states.values() for r in s.finish()],key=lambda r:r['start_ps'])
    issues = [{**i,'monitor':name} for name,s in states.items() for i in s.issues]
    return rows, issues, controls


def read_events(path):
    events, issues = [], []
    if path.is_file():
        for index,line in enumerate(path.read_text().splitlines()):
            try:
                events.append(json.loads(line))
            except json.JSONDecodeError:
                issues.append({'message':f'incomplete/invalid event line {index+1}; capture may have been interrupted'})
    return events, issues


def write_report(directory, plan, result):
    catalog = json.loads((ROOT/plan['report']['axi']['catalog']).read_text())
    events, issues = read_events(directory/'axi-events.jsonl')
    rows, correlation_issues, controls = correlate(events,catalog)
    starts = [e for e in controls if e['channel']=='capture_start']
    annotated = bool(starts) and starts[0].get('annotations_version',0)>=1
    actors_path=plan['report']['axi'].get('actors')
    actors=json.loads((ROOT/actors_path).read_text()).get('axi_actors',{}) if actors_path else {}
    for monitor in catalog['monitors']:
        monitor['actor']=actors.get(monitor['id'],{'kind':'interconnect' if monitor['role']=='link' else 'unspecified',
                                                  'label':'Inter-NoC AXI link' if monitor['role']=='link' else 'Actor not recorded in this report'})
    by_id={m['id']:m for m in catalog['monitors']}
    for row in rows:
        row['actor']=by_id[row['monitor']]['actor']
        error=row['response'] is not None and number(row['response'])>=2
        expected=row.get('expected_response')
        if row['status']=='complete' and expected is not None and number(expected)!=number(row['response']):
            row['issues'].append('response differs from the explicitly declared expectation')
        row['error_intent']=('expected' if expected is not None and error and number(expected)==number(row['response']) else
                             'undeclared' if error and row['role']=='initiator' and annotated else
                             'observed' if error else 'none')
        if row['error_intent']=='undeclared':
            row['issues'].append('initiator error response has no declared expectation')
    correlation_issues += [{'monitor':row['monitor'],'transaction':row['uid'],'message':message}
                           for row in rows for message in row['issues']]
    binding_complete = bool(starts) and set(starts[0]['monitors']) == {m['id'] for m in catalog['monitors']}
    if not binding_complete:
        issues.append({'message':'AXI capture did not bind every cataloged boundary; no complete capture is claimed'})
    periods = [e.get('period_ps') for e in controls if e['channel']=='clock_period']
    clock_period_ps = periods[0] if len(periods) == 1 and type(periods[0]) is int and periods[0] > 0 else None
    if periods and clock_period_ps is None:
        issues.append({'message':'AXI capture has invalid or duplicate measured clock period'})
    overflow = any(e['channel']=='capture_overflow' for e in controls)
    if overflow:
        issues.append({'message':'AXI capture overflowed its configured event limit'})
    try:
        sha = subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip()
        dirty = bool(subprocess.check_output(['git','status','--porcelain'],cwd=ROOT,text=True))
    except subprocess.CalledProcessError:
        sha, dirty = 'unknown', True
    payload = {'schema_version':2,'run':{'target':plan['target'],'commit':sha,'dirty':dirty,
                'annotations_available':annotated,
                'context':plan['report'].get('context',''),
                'engine':plan['engine'],'seed':plan.get('seed'),'result':result,
                'workflow_run_id':os.environ.get('GITHUB_RUN_ID'),
                'workflow_attempt':os.environ.get('GITHUB_RUN_ATTEMPT'),
                'expected_failure':plan.get('expect_failure'),'capture_bound':binding_complete,
                'event_count':len(events),'capture_overflow':overflow,
                'clock_period_ps':clock_period_ps},
               'sections':{'axi':{'monitors':catalog['monitors'],'transactions':rows,
                                 'phases':[e for e in controls if e['channel']=='phase'],
                                 'issues':issues+correlation_issues}}}
    memory_issues = []
    if plan['report'].get('memory'):
        from memory_report import read_memory_report
        section, memory_issues = read_memory_report(directory, rows, clock_period_ps)
        if section is not None:
            payload['sections']['memory'] = section
        if memory_issues:
            payload['sections']['axi']['issues'].extend(
                {'message':'memory: '+message} for message in memory_issues)
    (directory/'axi-transactions.json').write_text(json.dumps(payload,indent=2)+'\n')
    # Escape '<' even inside JSON strings: transaction text must never close
    # the embedded script element. All table/details text uses textContent.
    render_report(payload,directory/'report.html')
    # The existing AXI correlator remains the sole owner of AXI semantics.
    # Export its completed observations through the protocol-neutral view.
    import protocol_report
    protocols = protocol_report.build(directory, plan, axi_payload=payload)
    if protocols is not None:
        path = directory/'report.html'
        html = path.read_text()
        link = '<p><a href="protocols.html">Unified protocol explorer (AXI + other VIP streams)</a></p>'
        path.write_text(html.replace('<main>', '<main>'+link, 1))
    return {'transactions':len(rows),'events':len(events),'capture_bound':binding_complete,
            'overflow':overflow,'issues':len(issues)+len(correlation_issues)+len(memory_issues)}


def render_report(payload,path):
    data=json.dumps(payload,separators=(',',':')).replace('<','\\u003c')
    template=(ROOT/'tools/templates/run_report.html').read_text()
    Path(path).write_text(template.replace('__RUN_DATA__',data))
