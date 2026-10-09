"""Mechanical archive audit; conclusions and human acceptance remain separate."""
import hashlib,json,statistics
from pathlib import Path
S=Path(__file__).resolve().parent/'studies/2026-10-09-strata-usb4-7900xtx'
def load(p):return json.loads(p.read_text(encoding='utf-8'))
freeze=load(S/'freeze.json');summary=load(S/'summary.json');deployment=load(S/'deployment-status.json')
findings=[];counts={};usage_rows=[]
expected={f'{t}-local-r{r}' for t in ['D01','C01','W01','C02','A01','W02','C03','A02','E01','W03'] for r in ([1,2,3] if t in ['C03','A02','E01'] else [1])}
if hashlib.sha256((S/'tasks.json').read_bytes()).hexdigest()!='864716764b106dc678c06f80d80a08b77b2c5ad50da05ec7ab46fa76109f5df9':findings.append('original task fixture changed')
reviews=load(S/'editor-review.json')['entries']
for review in reviews:
    path=S/review['source']
    if not path.exists() or hashlib.sha256(path.read_bytes()).hexdigest()!=review['answer_sha256']:findings.append('editor SHA mismatch: '+review['source'])
for p in freeze['profiles']:
    main=list((S/'results'/p).glob('*/result.json'));names={f.parent.name for f in main}
    c={'main_sessions':len(main),'missing':sorted(expected-names),'extra':sorted(names-expected),'deployment_status':deployment[p]['status']}
    for group,pattern in [('preflight','*/result.json'),('thinking-complex','*/result.json'),('overthinking-native','*.json'),('speed-probes','*.json'),('preflight-probes','*.json'),('capacity','*.json')]:c[group]=len(list((S/group/p).glob(pattern)))
    if deployment[p]['status']=='scored':
        if names!=expected:findings.append(p+': main set incomplete')
        if c['overthinking-native']!=12 or c['speed-probes']!=3 or c['thinking-complex']!=1:findings.append(p+': control recordings incomplete')
        if len([r for r in reviews if r['profile']==p])!=3:findings.append(p+': writing review incomplete')
        if p!='halogen-w4b':
            native=S/'capacity-status'/f'{p}-32768-262144.json'
            if not native.exists():findings.append(p+': capacity native not closed')
            elif not load(native).get('stopped') and not (S/'capacity-status'/f'{p}-524288-524288-slack8.json').exists():findings.append(p+': corrected extension not closed after operational native completion')
    elif deployment[p]['status']!='deployment_failed':findings.append(p+': deployment pending')
    counts[p]=c
for group,pattern in [('results','*/*/result.json'),('preflight','*/*/result.json'),('thinking-complex','*/*/result.json'),('overthinking-native','*/*.json'),('speed-probes','*/*.json'),('preflight-probes','*/*.json'),('capacity','*/*.json')]:
    for f in sorted((S/group).glob(pattern)):
        d=load(f);u=d.get('usage') or d.get('response',{}).get('usage') or {}
        complete=d.get('usage_complete',not bool(d.get('error')))
        known=u.get('total_tokens') if isinstance(u.get('total_tokens'),int) else None
        usage_rows.append({'file':str(f.relative_to(S)).replace('\\','/'),'group':group,'known_total_tokens':known,'usage_complete':complete and known is not None})
        if group=='capacity' and not d.get('error'):
            fixture=load(S/'capacity-fixtures'/f"{d['context_target']}.json")
            sha=hashlib.sha256((S/'capacity-fixtures'/f"{d['context_target']}.json").read_bytes()).hexdigest()
            if d['fixture_sha256']!=sha:findings.append('capacity SHA mismatch: '+str(f.relative_to(S)))
            suffix='-slack8' if d.get('capacity_validation_correction') else ''
            resources=S/'resources'/d['profile']/f"{d['context_target']}-{d['kind']}{suffix}.jsonl"
            if not resources.exists():findings.append('missing resources: '+str(resources.relative_to(S)))
            else:
                samples=[json.loads(l) for l in resources.read_text().splitlines() if l.strip()]
                if not samples or any(x['xtx_vram_used'] is None for x in samples):findings.append('missing VRAM telemetry: '+str(resources.relative_to(S)))
if not (S/'restored-service.json').exists():findings.append('original service restoration pending')
else:
    restored=load(S/'restored-service.json')
    if not restored.get('original_unit_unchanged') or not restored.get('short_task',{}).get('grade',{}).get('pass'):findings.append('restoration verification failed')
if summary['status']!='main_complete':findings.append('summary not complete')
transport=load(S/'diagnostics/transport-failure-001/incident.json')
out={'status':'complete' if not findings else 'incomplete','integrity_findings':findings,'counts':counts,'known_total_tokens_all_recorded':sum(r['known_total_tokens'] or 0 for r in usage_rows),'unknown_usage_recordings':sum(not r['usage_complete'] for r in usage_rows),'recorded_model_test_recordings':len(usage_rows),'unsent_transport_recordings_separately_preserved':len(transport['records']),'token_ledger':usage_rows,'boundaries':'Task sessions may contain multiple HTTP calls; this counts archived recordings, not HTTP requests. All preflight, main/control and capacity recordings are separate. Restoration short task is separate from benchmark. An operationally completed capacity ladder may contain acceptance failures. Client connection-refused attempts proven unseen by the server are preserved as transport diagnostics and excluded from model scores.'}
(S/'audit.json').write_text(json.dumps(out,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
print(json.dumps({k:v for k,v in out.items() if k!='token_ledger'},ensure_ascii=False,indent=2))
