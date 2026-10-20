"""Recompute source-bound current/Preview results. No inference or raw-grade mutation."""
import csv,hashlib,json,statistics
from semantic_annotations import semantic_lc01
from pathlib import Path
S=Path(__file__).resolve().parent;B=S.parent/'2026-10-13-minimax-m31-vs-local-qwen'
PROFILES=['deepseek','minimax','preview'];TASKS=['D01','C01','W01','A01','C03','A02','W03']
def read(p):return json.loads(p.read_text(encoding='utf-8'))
def digest(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def med(values):
 values=[x for x in values if isinstance(x,(int,float))];return statistics.median(values) if values else None
def cached(u):return u.get('prompt_tokens_details',{}).get('cached_tokens',u.get('prompt_cache_hit_tokens'))
def native(turns):
 out={}
 for name,n,t in [('prefill','prompt_n','prompt_ms'),('decode','predicted_n','predicted_ms')]:
  ts=[x.get('timings') or {} for x in turns]
  out[name]=sum(x[n] for x in ts)*1000/sum(x[t] for x in ts) if ts and all(isinstance(x.get(n),(int,float)) and isinstance(x.get(t),(int,float)) and x[t]>0 for x in ts) else None
 return out
def metrics(turns):
 valid=[x for x in turns if isinstance(x.get('usage'),dict)]
 known=bool(turns) and len(valid)==len(turns) and all(all(isinstance(x['usage'].get(k),int) for k in ['prompt_tokens','completion_tokens','total_tokens']) for x in valid)
 usage={k:sum(x['usage'].get(k,0) for x in valid) for k in ['prompt_tokens','completion_tokens','total_tokens']}
 cs=[cached(x['usage']) for x in valid];rs=[x['usage'].get('completion_tokens_details',{}).get('reasoning_tokens') for x in valid]
 windows=[]
 for x in valid:
  starts=[x.get(k) for k in ['first_reasoning_s','first_content_s','first_tool_s'] if isinstance(x.get(k),(int,float))]
  elapsed=x.get('api_elapsed_s',x.get('elapsed_s'))
  windows.append(elapsed-min(starts) if starts and isinstance(elapsed,(int,float)) and elapsed>min(starts) else None)
 return {'usage':usage,'all_turn_usage_known':known,'cached_tokens':sum(cs) if cs and all(isinstance(x,int) for x in cs) else None,'reasoning_tokens':sum(rs) if rs and all(isinstance(x,int) for x in rs) else None,'reasoning_chars':sum(x.get('reasoning_chars',0) for x in turns),'native_speed':native(turns),'observed_generation_tokens_s':usage['completion_tokens']/sum(windows) if windows and all(x is not None and x>0 for x in windows) else None,'first_content_s_each':[x.get('first_content_s') for x in turns],'api_calls':len(turns)}
reviews=read(S/'editorial-review.json') if (S/'editorial-review.json').exists() else {'writing':[],'long_horizon':[],'context':[]}
oldreviews=read(B/'editorial-review.json');calls=[]
def editor(profile,kind,task,rn):
 rev=oldreviews if profile=='preview' else reviews
 return next((x for x in rev.get(kind,[]) if x['provider']==('minimax' if profile=='preview' else profile) and x['round']==rn and (x.get('task',task)==task)),None)
def addcalls(profile,category,task,rn,stage,turns,path):
 for i,x in enumerate(turns,1):
  u=x.get('usage') or {};ns=native([x]);calls.append({'profile':profile,'category':category,'task':task,'round':rn,'stage':stage,'turn':i,'api_elapsed_s':x.get('api_elapsed_s',x.get('elapsed_s')),'first_event_s':x.get('first_event_s'),'first_reasoning_s':x.get('first_reasoning_s'),'first_content_s':x.get('first_content_s'),'first_tool_s':x.get('first_tool_s'),'prompt_tokens':u.get('prompt_tokens'),'completion_tokens':u.get('completion_tokens'),'total_tokens':u.get('total_tokens'),'cached_tokens':cached(u),'reasoning_tokens':u.get('completion_tokens_details',{}).get('reasoning_tokens'),'reasoning_chars':x.get('reasoning_chars'),'native_prefill_tokens_s':ns['prefill'],'native_decode_tokens_s':ns['decode'],'finish_reason':x.get('finish_reason'),'error':x.get('error'),'source':str(path.relative_to(S)) if path.is_relative_to(S) else '../'+B.name+'/'+path.relative_to(B).as_posix(),'source_sha256':digest(path)})
def roundshort(profile,task,rn,variant):
 root,p=(B,'minimax') if profile=='preview' else (S,profile);f=root/f'results/short/{variant}/{p}/{task}-r{rn}/result.json'
 if not f.exists():return None
 d=read(f)
 if 'hidden_grading_s_excluded' not in d:return None
 ed=editor(profile,'writing',task,rn) if variant=='main' and task in ['W01','W03'] else None
 m=metrics(d['turns']);error=d.get('error');m['all_turn_usage_known']=m['all_turn_usage_known'] and not (error and (error.startswith(('HTTP','network')) or 'timed out' in error))
 hard=bool(d.get('grade',{}).get('pass'));full=hard and (bool(ed and ed['pass']) if task in ['W01','W03'] and variant=='main' else True)
 row={'round':rn,'elapsed_s':d['elapsed_s'],'hard_pass':hard,'complete_delivery':full,'grade':d.get('grade'),'editorial':ed,'error':error,'answer_sha256':digest(f.parent/'answer.txt'),'source':f.relative_to(root).as_posix(),**m}
 addcalls(profile,variant,task,rn,'',d['turns'],f)
 if error and not d['turns']:calls.append({'profile':profile,'category':variant,'task':task,'round':rn,'turn':1,'api_elapsed_s':d['elapsed_s'],'error':error,'source':row['source'],'source_sha256':digest(f)})
 return row
def group(rows):
 rows=[x for x in rows if x];return {'rounds':rows,'attempts':len(rows),'complete_deliveries':sum(x.get('complete_delivery',False) for x in rows),'elapsed_median_s':med([x.get('elapsed_s') for x in rows]),'output_tokens_median':med([x['usage']['completion_tokens'] for x in rows if x.get('all_turn_usage_known')]),'prefill_median_tokens_s':med([x['native_speed']['prefill'] for x in rows]),'decode_median_tokens_s':med([x['native_speed']['decode'] for x in rows]),'observed_generation_median_tokens_s':med([x.get('observed_generation_tokens_s') for x in rows]),'usage_sum_known_recorded':{k:sum(x['usage'][k] for x in rows) for k in ['prompt_tokens','completion_tokens','total_tokens']},'usage_has_unknown':any(not x.get('all_turn_usage_known') for x in rows)}
out={'study':S.name,'definitions':{'native_speed':'Unknown unless provider gives native compute counters; wall clock is never used to infer Prefill/Decode.','observed_generation':'sum completion tokens / sum(API elapsed minus earliest reasoning/content/tool event), per round then median; includes network and batching, not native Decode.','wait':'all attempts retained, hidden grading excluded; timing deviations disclosed separately.','quality':'strict raw grade and source-bound unblinded proxy editorial review; semantic clarifications separate.','token':'API-reported repeated history and model-specific tokenization; unknown failed calls are not zero.'},'profiles':{}}
for profile in PROFILES:
 p={'tasks':{},'depth':None,'long':[],'context':{}}
 for task in TASKS:p['tasks'][task]=group([roundshort(profile,task,rn,'main') for rn in [1,2]])
 p['depth']=group([roundshort(profile,'D01',rn,'depth') for rn in [1,2]])
 root,prov=(B,'minimax') if profile=='preview' else (S,profile)
 for rn in [1,2]:
  f=root/f'results/long/{prov}/r{rn}/record.json'
  if not f.exists():continue
  d=read(f)
  if 'hidden_grading_s_excluded' not in d:continue
  stages=[];ts=[]
  for st in d['stages']:
   tr=st['turns'];ts+=tr;sm=metrics(tr);stages.append({'id':st['id'],'elapsed_s':st.get('elapsed_s'),'hard_pass':st.get('grade',{}).get('pass',False),'finished_with_answer':st.get('finished_with_answer',False),'error':st.get('error'),'grade':st.get('grade'),**sm});addcalls(profile,'long','LH01',rn,st['id'],tr,f)
  ed=editor(profile,'long_horizon','LH01',rn);p['long'].append({'round':rn,'elapsed_s':d['elapsed_s'],'complete_delivery':bool(d.get('complete_delivery') and ed and ed['pass']),'hard_complete_delivery':d.get('complete_delivery',False),'stages':stages,'editorial':ed,'publication':d['stages'][-1].get('publication',{}) if d['stages'] else {},'error':d.get('error'),'source':f.relative_to(root).as_posix(),**metrics(ts)})
 if profile!='preview':
  for task in ['LC01','LC02']:
   rr=[]
   for rn in [1,2]:
    f=root/f'results/context/{prov}/{task}-r{rn}/result.json'
    if not f.exists():continue
    d=read(f);resp=d.get('response',{});c=resp.get('choices',[{}])[0];msg=c.get('message',{});tr={'usage':resp.get('usage'), 'reasoning_chars':len(msg.get('reasoning_content') or ''),'timings':resp.get('timings'),'finish_reason':c.get('finish_reason'),**d.get('latency',{})};ed=editor(profile,'context',task,rn) if task=='LC02' else None
    semantic=None
    if task=='LC01':
     try:
      semantic=semantic_lc01(d.get('content',''))['pass']
     except Exception:semantic=False
    if task=='LC02':
     try:
      ans=json.loads(d.get('content',''));checks=(d.get('grade') or {}).get('checks',{});semantic=all(v for k,v in checks.items() if k!='policy_and_amount') and ans.get('approved_policy') in ['v2','P-V2'] and type(ans.get('total_requested_cents')) is int and ans['total_requested_cents']==90000
     except Exception:semantic=False
    interpreted=bool(semantic and d.get('length_qualified') and c.get('finish_reason')!='length' and (ed and ed['pass'] if task=='LC02' else True))
    rr.append({'round':rn,'elapsed_s':d['elapsed_s'],'actual_prompt_tokens':d.get('actual_prompt_tokens'),'length_qualified':d.get('length_qualified',False),'prompt_sha256':d['prompt_sha256'],'hard_pass':d.get('complete_hard',False),'complete_delivery':bool(d.get('complete_hard') and (ed and ed['pass'] if task=='LC02' else True)),'semantic_core_correct':semantic,'interpretive_delivery':interpreted,'grade':d.get('grade'),'editorial':ed,'error':d.get('error'),'source':f.relative_to(root).as_posix(),'answer_sha256':digest(f.parent/'answer.txt') if (f.parent/'answer.txt').exists() else None,**metrics([tr])});addcalls(profile,'context',task,rn,'',[tr],f)
   p['context'][task]=group(rr)
 p['main_complete']=sum(x['complete_deliveries'] for x in p['tasks'].values());p['main_attempts']=sum(x['attempts'] for x in p['tasks'].values());p['core_complete']=p['main_complete']+sum(x['complete_delivery'] for x in p['long']);p['completed_case_count']=p['main_attempts']+p['depth']['attempts']+len(p['long'])+sum(x['attempts'] for x in p['context'].values());out['profiles'][profile]=p
out['complete_collection']=all(out['profiles'][p]['completed_case_count']==22 for p in ['deepseek','minimax'])
out['api_calls_known_or_failed']=len(calls);out['unknown_usage_call_rows']=sum(not isinstance(c.get('total_tokens'),int) for c in calls)
(S/'summary-progress.json').write_text(json.dumps(out,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
if out['complete_collection']:(S/'summary.json').write_text(json.dumps(out,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
keys=list(dict.fromkeys(k for r in calls for k in r))
with (S/'all-turn-timings.csv').open('w',encoding='utf-8-sig',newline='') as f:
 w=csv.DictWriter(f,fieldnames=keys);w.writeheader();w.writerows(calls)
print(json.dumps({'complete_collection':out['complete_collection'],'profiles':{p:{k:x[k] for k in ['main_complete','main_attempts','core_complete','completed_case_count']} for p,x in out['profiles'].items()},'unknown_usage_call_rows':out['unknown_usage_call_rows']},ensure_ascii=False))
