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
