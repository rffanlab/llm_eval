"""Registered results only. Missing/failing deployment is not a zero task score."""
import json,statistics,hashlib
from pathlib import Path
S=Path(__file__).resolve().parent/'studies/2026-10-09-strata-usb4-7900xtx'
def load(p):return json.loads(p.read_text(encoding='utf-8'))
profiles=load(S/'freeze.json')['profiles']
tasks=json.loads((S/'tasks.json').read_bytes())['tasks']
deploy=load(S/'deployment-status.json') if (S/'deployment-status.json').exists() else {}
reviews=load(S/'editor-review.json')['entries'] if (S/'editor-review.json').exists() else []
adjud=load(S/'adjudications.json')['entries'] if (S/'adjudications.json').exists() else []
rows=[];totals={};thinking=[];capacity={}
for profile in profiles:
    for task in tasks:
        files=sorted((S/'results'/profile).glob(task['id']+'-local-r*/result.json'))
        ds=[load(f) for f in files]
        if not ds:continue
        accepted=[];usable=[];timely=[]
        limit=60 if task['id'] in ['D01','C01','W01','C02','A01'] else 240
        for f,d in zip(files,ds):
            ok=d['grade']['pass']
            for a in adjud:
                if (a['profile'],a['task'],a['round'])==(profile,task['id'],d['round']):
                    assert a['answer_sha256']==hashlib.sha256((f.parent/'answer.txt').read_bytes()).hexdigest()
                    ok=a['acceptance_pass']
            accepted.append(ok)
            review=next((r for r in reviews if (r['profile'],r['task'])==(profile,task['id'])),None)
            usable.append(ok and (task['domain']!='writing' or bool(review and review['scores']['total']>=16)))
            timely.append(usable[-1] and d['elapsed_s']<=limit)
        rows.append({'profile':profile,'task':task['id'],'domain':task['domain'],'n':len(ds),'raw_passes':sum(d['grade']['pass'] for d in ds),'accepted_passes':sum(accepted),'complete_deliverables':sum(usable),'latency_limit_s':limit,'timely_complete_deliverables':sum(timely),'elapsed_s':[d['elapsed_s'] for d in ds],'median_elapsed_s':statistics.median(d['elapsed_s'] for d in ds),'median_total_tokens':statistics.median(d['usage']['total_tokens'] for d in ds) if all(d['usage_complete'] for d in ds) else None,'known_total_tokens':sum(d['usage']['total_tokens'] for d in ds),'unknown_usage_sessions':sum(not d['usage_complete'] for d in ds),'answers':[str(f.parent.relative_to(S)) for f in files]})
    pr=[r for r in rows if r['profile']==profile]
    probes=[load(f) for f in sorted((S/'speed-probes'/profile).glob('*.json'))]
    valid=[d for d in probes if d.get('response',{}).get('usage',{}).get('completion_tokens')==512 and d.get('response',{}).get('timings',{}).get('predicted_n')==512]
    totals[profile]={'deployment':deploy.get(profile,{'status':'pending'}),'main_sessions':sum(r['n'] for r in pr),'raw_passes':sum(r['raw_passes'] for r in pr) if pr else None,'accepted_passes':sum(r['accepted_passes'] for r in pr) if pr else None,'complete_deliverables':sum(r['complete_deliverables'] for r in pr) if pr else None,'known_main_tokens':sum(r['known_total_tokens'] for r in pr),'known_main_elapsed_s':sum(sum(r['elapsed_s']) for r in pr),'unknown_usage_sessions':sum(r['unknown_usage_sessions'] for r in pr),'speed_probe_n':len(probes),'valid_512_n':len(valid),'median_decode_tps':statistics.median(d['response']['timings']['predicted_per_second'] for d in valid) if valid else None}
    for task in ['O01','O02','O03']:
        modes={}
        for mode in ['on','off']:
            ds=[load(f) for f in sorted((S/'overthinking-native'/profile).glob(f'{task}-{mode}-r*.json'))]
            if not ds:continue
            output=[d.get('response',{}).get('usage',{}).get('completion_tokens') for d in ds]
            thought=[d.get('response',{}).get('usage',{}).get('completion_tokens_details',{}).get('reasoning_tokens') for d in ds]
            modes[mode]={'n':len(ds),'passes':sum(d['pass'] for d in ds),'median_elapsed_s':statistics.median(d['elapsed_s'] for d in ds),'median_output_tokens':statistics.median(output) if all(isinstance(x,int) for x in output) else None,'median_reasoning_tokens':statistics.median(thought) if all(isinstance(x,int) for x in thought) else None}
        flag=None
        if set(modes)=={'on','off'} and all(m['n']==2 and m['passes']==2 and m['median_output_tokens'] is not None and m['median_reasoning_tokens'] is not None for m in modes.values()):
            on,off=modes['on'],modes['off']
            flag=(on['median_output_tokens']>=2*off['median_output_tokens'] and on['median_elapsed_s']>=2*off['median_elapsed_s'] and on['median_reasoning_tokens']-off['median_reasoning_tokens']>=50 and on['median_elapsed_s']-off['median_elapsed_s']>=1)
        thinking.append({'profile':profile,'task':task,'modes':modes,'registered_overthinking_flag':flag})
    capacity[profile]=[load(f) for f in sorted((S/'capacity'/profile).glob('*.json'))]
complete=all(t['main_sessions']==16 or t['deployment']['status']=='deployment_failed' for t in totals.values())
out={'status':'main_complete' if complete else 'incomplete','profiles':profiles,'totals':totals,'tasks':rows,'thinking':thinking,'capacity':capacity,'notes':'Writing editor review and owner approval are separate. Capacity n=1, independent token account.'}
(S/'summary.json').write_text(json.dumps(out,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
print(json.dumps({'status':out['status'],'totals':totals},ensure_ascii=False,indent=2))
