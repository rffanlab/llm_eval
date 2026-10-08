"""Offline integrity audit for this study; does not turn task failures into successes."""
import hashlib
import json
from pathlib import Path

ROOT=Path(__file__).resolve().parent
STUDY=ROOT/'studies/2026-10-08-halogen-three-way'
profiles=['old-w4b','new-v2','swift-v2']
raw=(STUDY/'tasks.json').read_bytes();suite=json.loads(raw);digest=hashlib.sha256(raw).hexdigest()
tasks={x['id']:x for x in suite['tasks']}
expected={(t,1) for t in tasks}|{(t,r) for t in suite['repeat_tasks'] for r in [2,3]}
short_digest=hashlib.sha256((STUDY/'overthinking-tasks.json').read_bytes()).hexdigest()
native_digest=hashlib.sha256((STUDY/'overthinking-native-tasks.json').read_bytes()).hexdigest()
findings=[];categories={};counts={};failures=[];unknown=[]

for profile in profiles:
    found=set()
    for file in sorted((STUDY/'results'/profile).glob('*/result.json')):
        d=json.loads(file.read_text(encoding='utf-8'));pair=(d['task'],d['round']);found.add(pair)
        if d['fixture_sha256']!=digest:findings.append(str(file.relative_to(STUDY))+': fixture hash')
        if d['profile']!=profile:findings.append(str(file.relative_to(STUDY))+': profile')
        if d['parameters']!={'temperature':0,'enable_thinking':True,'max_tokens':tasks[d['task']]['max_tokens'],'stream':False}:findings.append(str(file.relative_to(STUDY))+': parameters')
        if not d['grade']['pass']:failures.append({'profile':profile,'task':d['task'],'round':d['round'],'grade':d['grade']})
        if not d['usage_complete']:unknown.append(str(file.relative_to(STUDY)))
        for k in ['prompt_tokens','completion_tokens','total_tokens']:
            if sum(t['usage'][k] for t in d['turns'])!=d['usage'][k]:findings.append(str(file.relative_to(STUDY))+': cumulative '+k)
    counts[profile]={'main_sessions':len(found),'missing':sorted(expected-found),'extra':sorted(found-expected)}
    for file in sorted((STUDY/'overthinking'/profile).glob('*.json')):
        d=json.loads(file.read_text(encoding='utf-8'))
        if d['fixture_sha256']!=short_digest:findings.append(str(file.relative_to(STUDY))+': short fixture hash')
        if d['payload']['enable_thinking']!=(d['thinking']=='on'):findings.append(str(file.relative_to(STUDY))+': short mode')
        if d['payload']['temperature']!=0 or d['payload']['max_tokens']!=1024:findings.append(str(file.relative_to(STUDY))+': short parameters')
    counts[profile]['short_sessions']=len(list((STUDY/'overthinking'/profile).glob('*.json')))
    natives=list((STUDY/'overthinking-native'/profile).glob('*.json'))
    counts[profile]['native_short_sessions']=len(natives)
    for file in natives:
        d=json.loads(file.read_text(encoding='utf-8'))
        if d['fixture_sha256']!=native_digest or d['payload']['max_tokens']!=4096:findings.append(str(file.relative_to(STUDY))+': native fixture or budget')
        if d['payload']['enable_thinking']!=(d['thinking']=='on'):findings.append(str(file.relative_to(STUDY))+': native mode')
    controls=list((STUDY/'thinking-complex'/profile).glob('*/result.json'))
    counts[profile]['complex_off_sessions']=len(controls)
    for file in controls:
        d=json.loads(file.read_text(encoding='utf-8'))
        if d['parameters']['enable_thinking'] is not False or d['task']!='C03' or d['fixture_sha256']!=digest:findings.append(str(file.relative_to(STUDY))+': complex control')
    probes=[json.loads(f.read_text(encoding='utf-8')) for f in (STUDY/'speed-probes'/profile).glob('*.json')]
    counts[profile]['fixed_length_probes']=sum(d.get('response',{}).get('usage',{}).get('completion_tokens')==512 and d.get('response',{}).get('timings',{}).get('predicted_n')==512 for d in probes)
    counts[profile]['recorded_probes']=len(probes)

for category in ['results','preflight','thinking-complex','speed-probes','overthinking','overthinking-native']:
    tokens=0;recorded=0;incomplete=0
    for file in (STUDY/category).rglob('*.json'):
        d=json.loads(file.read_text(encoding='utf-8'))
        usage=d.get('usage') or d.get('response',{}).get('usage',{})
        if 'task' not in d and 'round' not in d:continue
        recorded+=1
        if isinstance(usage.get('total_tokens'),int):tokens+=usage['total_tokens']
        else:incomplete+=1
    categories[category]={'recorded_sessions':recorded,'known_total_tokens':tokens,'missing_usage_sessions':incomplete}
complete=all(not v['missing'] and not v['extra'] and v['main_sessions']==16 and v['short_sessions']==12 and v['native_short_sessions']==12 and v['complex_off_sessions']==1 and v['recorded_probes']==3 for v in counts.values())
out={'status':'complete' if complete and not findings else 'incomplete_or_integrity_findings','fixture_sha256':digest,'integrity_findings':findings,'counts':counts,'raw_task_failures':failures,'unknown_main_usage':unknown,'category_usage':categories,'known_total_tokens_all_recorded':sum(c['known_total_tokens'] for c in categories.values()),'cancelled_attempt_usage':'unknown, recorded separately in operational-incidents; never assigned zero','timing_boundary':'API request through final reply including simulator tool turnarounds; excludes model loading, separate functional grading and editorial review'}
(STUDY/'audit.json').write_text(json.dumps(out,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
print(json.dumps({k:out[k] for k in ['status','integrity_findings','counts','category_usage']},ensure_ascii=False))
