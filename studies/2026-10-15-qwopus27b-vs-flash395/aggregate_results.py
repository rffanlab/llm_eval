"""Offline result aggregation; never calls a model or changes frozen evaluation files."""
import argparse,hashlib,json,statistics
from pathlib import Path
from native_speed import aggregate_turns,summarize_rounds as summarize_counter_rounds
from native_engine_speed import aggregate_native_rates
S=Path(__file__).resolve().parent
PROFILES=json.loads((S/'profiles.json').read_text())
TASKS=['D01','C01','W01','A01','C03','A02','W03']
WRITING={'W01','W03'}
def read(p):return json.loads(p.read_text(encoding='utf-8'))
def counter(x):return isinstance(x,int) and not isinstance(x,bool) and x>=0
def usage(d):
 if 'turns' in d and not d['turns']:return None
 if 'stages' in d and not any(t.get('usage') for s in d['stages'] for t in s.get('turns',[])):return None
 u=d.get('usage')
 return u if d.get('usage_complete',True) and isinstance(u,dict) and all(counter(u.get(k)) for k in ['prompt_tokens','completion_tokens','total_tokens']) else None
def total_usage(turns):
 rows=[t.get('usage') for t in turns]
 if not rows or not all(isinstance(u,dict) and all(counter(u.get(k)) for k in ['prompt_tokens','completion_tokens','total_tokens']) for u in rows):return None
 return {k:sum(u[k] for u in rows) for k in ['prompt_tokens','completion_tokens','total_tokens']}
def speed(turns,error=None):
 turns=list(turns)
 # A failed stream may have generated tokens that never received final timing.
 fully_observed_failure={'output_truncated','stage_call_budget','episode_wall_budget','episode_completion_budget','total_output_budget_exhausted','task_wall_budget','agent_reply_budget_exhausted'}
 if error and error not in fully_observed_failure:turns.append({})
 return {**aggregate_turns(turns),'engine_native':aggregate_native_rates(turns)}
def editor(path,answer,reviews):
 key=path.relative_to(S).as_posix();review=reviews.get(key)
 if review is None:return None
 digest=hashlib.sha256(answer.encode()).hexdigest()
 assert review['answer_sha256']==digest,'review text changed: '+key
 values=review['scores'];assert set(values)=={'facts','complete','clear','useful'} and all(isinstance(x,int) and 0<=x<=5 for x in values.values())
 return {**review,'answer_source':key,'total':sum(values.values()),'pass':values['facts']>=3 and sum(values.values())>=16}
def resources(folder):
 p=folder/'resources.jsonl'
 if not p.exists():return None
 rows=[];invalid=0
 for line in p.read_text().splitlines():
  try:rows.append(json.loads(line))
  except (ValueError,TypeError):invalid+=1
 g=[g for r in rows for g in r.get('gpu',[])]
 def greatest(key):
  vals=[r[key] for r in g if isinstance(r.get(key),(int,float))];return max(vals) if vals else None
 available=[r['MemAvailable'] for r in rows if counter(r.get('MemAvailable'))]
 return {'samples':len(rows),'invalid_rows':invalid,'gpu_probe_errors':sum(bool(r.get('gpu_probe_error')) for r in rows),'minimum_MemAvailable_bytes':min(available) if available else None,'peak_VRAM_bytes':greatest('VRAM'),'peak_GTT_bytes':greatest('GTT'),'peak_sampled_power_mw':greatest('power_mw'),'peak_sampled_temperature_c':greatest('temperature_c')}
def median(values):
 return statistics.median(values) if values and all(isinstance(x,(int,float)) and not isinstance(x,bool) for x in values) else None
def summarize_rounds(rows):
 out=summarize_counter_rounds(rows)
 for name in ['prefill','decode']:
  values=[r['native_speed']['engine_native'][name+'_tokens_s'] for r in rows]
  out['engine_'+name+'_rounds_measured']=sum(x is not None for x in values)
  out['engine_'+name+'_median_tokens_s']=median(values)
 return out
def summarize(rows):
 return {**summarize_rounds(rows),'rounds':rows,'elapsed_median_s':median([r['elapsed_s'] for r in rows]),'input_median_tokens':median([(r.get('usage') or {}).get('prompt_tokens') for r in rows]),'output_median_tokens':median([(r.get('usage') or {}).get('completion_tokens') for r in rows]),'hard_pass_count':sum(r.get('hard_pass') is True for r in rows),'delivery_pass_count':sum(r.get('delivery_pass') is True for r in rows),'delivery_pending':sum(r.get('delivery_pass') is None for r in rows),'two_round_delivery':len(rows)==2 and all(r.get('delivery_pass') is True for r in rows)}
def build(partial=False):
 reviews=read(S/'editorial-review.json')['reviews'] if (S/'editorial-review.json').exists() else {}
 missing=[];result={'profiles':{},'missing':missing,'timing_definition':'Per round sum native new prompt_n/prompt_ms and predicted_n/predicted_ms; median of round ratios. Cached tokens separate. Missing native times stay unknown. Short/long full waits include API/tools/admission, exclude hidden grading. Speed probes report complete HTTP/SSE wait, excluding admission. Timing coverage is separate from delivery success; a fully timed truncated answer or stage-call-budget failure retains its observed native rates.','review_definition':'Automated hard checks plus primary assistant editorial facts/complete/clear/useful, each0..5, >=16 and facts>=3; not blinded or owner approval.'}
 for profile in PROFILES:
  out={'profile':PROFILES[profile],'short':{},'thinking':{},'long':{},'speed':{}}
  result['profiles'][profile]=out
  for variant,tasks in [('main',TASKS),('depth',['D01'])]:
   for task in tasks:
    rounds=[]
    for round_ in [1,2]:
     p=S/'results/short'/profile/variant/'local'/(task+'-r'+str(round_))/'result.json'
     if not p.exists():missing.append(p.relative_to(S).as_posix());continue
     d=read(p);assert d['profile']==profile and d['task']==task and d['round']==round_ and d['variant']==variant
     e=editor(p.parent/'answer.txt',d.get('content') or '',reviews) if task in WRITING else None
     hard=d.get('grade',{}).get('pass') is True and not d.get('error')
     delivery=hard and e['pass'] if e is not None else (None if task in WRITING and hard else hard)
     rounds.append({'round':round_,'source':p.relative_to(S).as_posix(),'elapsed_s':d['elapsed_s'],'usage':usage(d),'observed_usage':d.get('usage'),'usage_complete':d.get('usage_complete'),'error':d.get('error'),'native_speed':speed(d.get('turns',[]),d.get('error')),'hard_pass':hard,'delivery_pass':delivery,'grade':d.get('grade'),'editorial':e,'reasoning_chars':d.get('reasoning_chars'),'api_wait_s':sum(t.get('api_elapsed_s',0) for t in d['turns']),'tool_calls':len(d.get('tool_trace',[])),'resources':resources(p.parent)})
    (out['short'] if variant=='main' else out['thinking'])[task]=summarize(rounds)
  episodes=[]
  for round_ in [1,2]:
   p=S/'results/long'/profile/('r'+str(round_))/'record.json'
   if not p.exists():missing.append(p.relative_to(S).as_posix());continue
   d=read(p);stages=[];all_turns=[]
   for stage in d.get('stages',[]):
    turns=stage['turns'];all_turns+=turns
    stages.append({'id':stage['id'],'name':stage['name'],'elapsed_s':stage.get('elapsed_s'),'usage':total_usage(turns),'error':stage.get('error'),'native_speed':speed(turns,stage.get('error')),'hard_pass':stage.get('grade',{}).get('pass') is True and not stage.get('error'),'delivery_pass':stage.get('grade',{}).get('pass') is True and stage.get('finished_with_answer') is True and not stage.get('error'),'finished_with_answer':stage.get('finished_with_answer'),'grade':stage.get('grade'),'calls':len(turns),'tool_calls':len(stage.get('tool_events',[])),'api_wait_s':sum(t.get('api_elapsed_s',t.get('elapsed_s',0)) for t in turns),'reasoning_chars':sum(t.get('reasoning_chars',0) for t in turns)})
   report=(p.parent/'workspace/delivery.md').read_text(encoding='utf-8') if (p.parent/'workspace/delivery.md').exists() else ''
   e=editor(p.parent/'workspace/delivery.md',report,reviews)
   for stage in stages:
    if stage['id']=='S4':
     stage['editorial']=e
     stage['delivery_pass']=(stage['delivery_pass'] and e['pass']) if e is not None else (None if stage['delivery_pass'] else False)
   hard=d.get('complete_delivery') is True and not d.get('error') and d.get('elapsed_s',float('inf'))<=2400 and (usage(d) or {}).get('completion_tokens',65537)<=65536
   delivery=hard and e['pass'] if e is not None else (None if hard else False)
   episodes.append({'round':round_,'source':p.relative_to(S).as_posix(),'elapsed_s':d.get('elapsed_s'),'usage':usage(d),'observed_usage':d.get('usage'),'usage_complete':d.get('usage_complete'),'error':d.get('error'),'hard_pass':hard,'delivery_pass':delivery,'editorial':e,'native_speed':speed(all_turns,d.get('error')),'stages':stages,'resources':resources(p.parent)})
  out['long']['episode']=summarize(episodes)
  for stage_id in ['S1','S2','S3','S4']:
   rows=[{'round':e['round'],**stage} for e in episodes for stage in e['stages'] if stage['id']==stage_id]
   out['long'][stage_id]=summarize(rows)
  for kind in ['short512','prompt4k','prompt32k']:
   rows=[]
   for round_ in [1,2,3]:
    p=S/'results/speed'/profile/(kind+'-r'+str(round_))/'result.json'
    if not p.exists():missing.append(p.relative_to(S).as_posix());continue
    d=read(p);response=d.get('response',{});turn={'timings':response.get('timings')}
    rows.append({'round':round_,'source':p.relative_to(S).as_posix(),'elapsed_s':d.get('latency',{}).get('api_elapsed_s'),'usage':usage(response),'error':d.get('error'),'finish_reason':(response.get('choices') or [{}])[0].get('finish_reason'),'quality_scored':False,'native_speed':speed([turn],d.get('error'))})
   out['speed'][kind]=summarize(rows)
  out['main_short_delivery_count']=sum(t['delivery_pass_count'] for t in out['short'].values())
  out['main_short_rounds_recorded']=sum(len(t['rounds']) for t in out['short'].values())
  out['main_short_editorial_pending']=sum(t['delivery_pending'] for t in out['short'].values())
 result['results_complete']=not missing
 result['all_editorial_complete']=not any(o['main_short_editorial_pending'] or o['long']['episode']['delivery_pending'] for o in result['profiles'].values())
 if not partial:assert result['results_complete'] and result['all_editorial_complete'],'Missing cases or required editorial reviews; use --partial for a progress snapshot'
 return result
if __name__=='__main__':
 a=argparse.ArgumentParser();a.add_argument('--partial',action='store_true');args=a.parse_args();d=build(args.partial)
 name='summary-progress.json' if args.partial else 'summary.json';(S/name).write_bytes((json.dumps(d,ensure_ascii=False,indent=2)+'\n').encode())
 print(json.dumps({'output':name,'missing_cases':len(d['missing']),'results_complete':d['results_complete'],'editorial_complete':d['all_editorial_complete']}))
