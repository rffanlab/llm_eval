"""Additional native engine rate view; frozen counter/time series remains unchanged."""
import math
def number(x):return isinstance(x,(int,float)) and not isinstance(x,bool) and math.isfinite(x)
def aggregate_native_rates(turns):
 turns=list(turns)
 out={'calls_total':len(turns),'definition':'duration-weighted engine reported rate; not an arithmetic mean of call rates'}
 for name,rate_key,time_key in [('prefill','prompt_per_second','prompt_ms'),('decode','predicted_per_second','predicted_ms')]:
  rows=[]
  for turn in turns:
   t=turn.get('timings') or {};rate,ms=t.get(rate_key),t.get(time_key)
   if number(rate) and rate>=0 and number(ms) and ms>0:rows.append((rate,ms))
   elif number(rate) and number(ms) and rate==0 and ms==0 and isinstance(t.get('prompt_n' if name=='prefill' else 'predicted_n'),int) and not isinstance(t.get('prompt_n' if name=='prefill' else 'predicted_n'),bool) and t['prompt_n' if name=='prefill' else 'predicted_n']==0:rows.append((0,0))
  complete=bool(turns) and len(rows)==len(turns);duration=sum(ms for _,ms in rows)
  out[name+'_calls_measured']=len(rows);out[name+'_timing_complete']=complete
  out[name+'_ms_measured']=duration
  out[name+'_tokens_s']=sum(rate*ms for rate,ms in rows)/duration if complete and duration>0 and any(rate>0 for rate,_ in rows) else None
 return out
