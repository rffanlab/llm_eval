"""Read archived episodes only; never call inference endpoints."""
import hashlib,json,statistics
from pathlib import Path
S=Path(__file__).resolve().parent
def load(p):return json.loads(p.read_text(encoding='utf-8'))
def median(x):return statistics.median(x) if x else None
def main():
    profiles={};episodes=[]
    for p in sorted((S/'results').glob('*/r*/record.json')):
        r=load(p);assert len(r['stages'])==4 and not r.get('error'),(p,r.get('error'))
        root=p.parent;res=[json.loads(l) for l in (root/'resources.jsonl').read_text().splitlines() if l.strip()]
        stages=[]
        for s in r['stages']:
            turns=s['turns'];u={k:sum(t.get('usage',{}).get(k,0) for t in turns) for k in ['prompt_tokens','completion_tokens','total_tokens']}
            native=[t.get('timings') or {} for t in turns]
            first_pass=next((e['turn'] for e in s['tool_events'] if e['tool']=='run_tests' and e['result'].get('pass')),None)
            after_pass_writes=sum(e['tool']=='write_file' and json.loads(e['arguments']).get('path')=='workflow.py' and first_pass is not None and e['turn']>first_pass for e in s['tool_events'])
            stages.append({'id':s['id'],'elapsed_s':s['elapsed_s'],'calls':len(turns),'tools':len(s['tool_events']),'hard_pass':s['grade']['pass'],'checks_passed':s['grade']['passed'],'checks_total':s['grade']['total'],'usage':u,'reasoning_chars':sum(t.get('reasoning_chars',0) for t in turns),'error':s.get('error'),'finished_with_answer':s['finished_with_answer'],'failed_checks':[c['name'] for c in s['grade']['checks'] if not c['pass']], 'native_prompt_ms':sum(n.get('prompt_ms',0) for n in native) if all('prompt_ms' in n for n in native) else None,'native_decode_ms':sum(n.get('predicted_ms',0) for n in native) if all('predicted_ms' in n for n in native) else None,'writes_after_visible_test_pass':after_pass_writes})
        exact_repeat=0;events=load(root/'tool-ledger.json')
        for a,b in zip(events,events[1:]):
            if a['tool']==b['tool'] and a['arguments']==b['arguments']:exact_repeat+=1
        row={'profile':r['profile'],'round':r['round'],'runner_complete_delivery':r['complete_delivery'],'elapsed_s':r['elapsed_s'],'usage':r['usage'],'usage_complete':r['usage_complete'],'calls':sum(s['calls'] for s in stages),'tool_calls':r['tool_calls'],'reasoning_chars':r['reasoning_chars'],'stages':stages,'min_MemAvailable_GiB':min(x['MemAvailable_bytes'] for x in res)/2**30,'max_GPU_GTT_VRAM_GiB':max(sum(g['GTT']+g['VRAM'] for g in x['gpu']) for x in res)/2**30,'consecutive_same_tool_arguments':exact_repeat,'writes_after_visible_test_pass':sum(s['writes_after_visible_test_pass'] for s in stages),'max_prompt_tokens_per_call':max(t['usage']['prompt_tokens'] for s in r['stages'] for t in s['turns'] if 'usage' in t and t['usage']),'record_sha256':hashlib.sha256(p.read_bytes()).hexdigest(),'source':p.relative_to(S).as_posix()}
        episodes.append(row);profiles.setdefault(r['profile'],[]).append(row)
    out={'episodes':episodes,'profiles':{},'denominator':'two complete persistent episodes per deployment; four dependent stages each','timing':'stage/episode waiting includes API, visible tools and admission; model loading, hidden grading and editorial review excluded','reasoning_unit':'characters, not tokens; reasoning tokens not separately inferred'}
    for name,rows in profiles.items():
        assert len(rows)==2
        out['profiles'][name]={'runner_complete_delivery':sum(r['runner_complete_delivery'] for r in rows),'episodes':2,'median_elapsed_s':median([r['elapsed_s'] for r in rows]),'elapsed_each_s':[r['elapsed_s'] for r in rows],'usage_sum':{k:sum(r['usage'][k] for r in rows) for k in ['prompt_tokens','completion_tokens','total_tokens']},'calls_sum':sum(r['calls'] for r in rows),'tools_sum':sum(r['tool_calls'] for r in rows),'reasoning_chars_sum':sum(r['reasoning_chars'] for r in rows),'min_MemAvailable_GiB':min(r['min_MemAvailable_GiB'] for r in rows),'max_GPU_GTT_VRAM_GiB':max(r['max_GPU_GTT_VRAM_GiB'] for r in rows),'stages':{s:{'hard_pass_count':sum(next(x for x in r['stages'] if x['id']==s)['hard_pass'] for r in rows),'median_elapsed_s':median([next(x for x in r['stages'] if x['id']==s)['elapsed_s'] for r in rows]),'calls_each':[next(x for x in r['stages'] if x['id']==s)['calls'] for r in rows],'checks_each':[str(next(x for x in r['stages'] if x['id']==s)['checks_passed'])+'/'+str(next(x for x in r['stages'] if x['id']==s)['checks_total']) for r in rows],'completion_tokens_sum':sum(next(x for x in r['stages'] if x['id']==s)['usage']['completion_tokens'] for r in rows),'reasoning_chars_sum':sum(next(x for x in r['stages'] if x['id']==s)['reasoning_chars'] for r in rows)} for s in ['S1','S2','S3','S4']}}
    (S/'summary.json').write_text(json.dumps(out,ensure_ascii=False,indent=2)+'\n',encoding='utf-8');print(json.dumps(out['profiles'],ensure_ascii=False,indent=2))
if __name__=='__main__':main()
