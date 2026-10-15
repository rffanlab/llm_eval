"""Offline exporter for the 2026-10-16 Flash parameter tuning study.
Reads completed local artifacts only; never calls a model or alters raw/frozen inputs.
"""
from __future__ import annotations
import csv,json,math,pathlib,statistics
S=pathlib.Path(__file__).resolve().parent
TASKS=['D01','C01','W01','A01','C03','A02','W03']
PHASES=('calibrate','validate')
SPEED_KINDS=('prompt4k','prompt32k')

def read(p): return json.loads(p.read_text(encoding='utf-8'))
def finite(x): return isinstance(x,(int,float)) and not isinstance(x,bool) and math.isfinite(x)
def counter(x): return isinstance(x,int) and not isinstance(x,bool) and x>=0
def native(turns):
    out={'calls_total':len(turns)}
    for label,nkey,tkey in [('prefill','prompt_n','prompt_ms'),('decode','predicted_n','predicted_ms')]:
        valid=[]
        for t in turns:
            q=t.get('timings') or {}; n=q.get(nkey); ms=q.get(tkey)
            if counter(n) and finite(ms) and (ms>0 or (n==0 and ms==0)): valid.append((n,ms))
        complete=bool(turns) and len(valid)==len(turns); nt=sum(x[0] for x in valid); tm=sum(x[1] for x in valid)
        out.update({label+'_calls_measured':len(valid),label+'_timing_complete':complete,label+'_tokens_measured':nt,label+'_ms_measured':tm,label+'_tokens_s':nt*1000/tm if complete and nt>0 and tm>0 else None})
    c=[(t.get('timings') or {}).get('cache_n') for t in turns];out['cached_tokens']=sum(c) if all(counter(x) for x in c) else None
    return out
def usage(d):
    u=d.get('usage');return u if d.get('usage_complete',True) and isinstance(u,dict) and all(counter(u.get(k)) for k in ('prompt_tokens','completion_tokens','total_tokens')) else None
def editorial(d):
    e=d.get('editorial') or {};return e.get('total') if isinstance(e,dict) else None
def grade_counts(g):
    g=g or {}; checks=g.get('tests') if isinstance(g,dict) else None
    if not isinstance(checks,list): checks=g.get('checks') if isinstance(g,dict) else None
    if isinstance(checks,list): return sum(x.get('pass') is True for x in checks if isinstance(x,dict)),len(checks)
    if isinstance(checks,dict): return sum(x is True for x in checks.values()),len(checks)
    return g.get('tests_passed',g.get('passed')),g.get('tests_total',g.get('total'))
def row_from_summary(phase,profile,kind,task,round_,sr):
    n=sr.get('native_speed') or {};u=sr.get('usage') or {};obs=sr.get('observed_usage') or {};g=sr.get('grade') or {};passed,total=grade_counts(g)
    return {'phase':phase,'profile':profile,'kind':kind,'task':task,'round':round_,'source':sr.get('source'),'full_wait_s':sr.get('elapsed_s'),'api_wait_s':sr.get('api_wait_s'),'prefill_tokens_s':n.get('prefill_tokens_s'),'decode_tokens_s':n.get('decode_tokens_s'),'prefill_timing_complete':n.get('prefill_timing_complete'),'decode_timing_complete':n.get('decode_timing_complete'),'native_new_input_tokens':n.get('prefill_tokens_measured'),'native_generated_tokens':n.get('decode_tokens_measured'),'native_prefill_ms':n.get('prefill_ms_measured'),'native_decode_ms':n.get('decode_ms_measured'),'cached_tokens':n.get('cached_tokens'),'api_input_tokens':u.get('prompt_tokens'),'api_output_tokens':u.get('completion_tokens'),'api_total_tokens':u.get('total_tokens'),'observed_api_input_tokens':obs.get('prompt_tokens'),'observed_api_output_tokens':obs.get('completion_tokens'),'usage_complete':sr.get('usage_complete'),'hard_pass':sr.get('hard_pass'),'delivery_pass':sr.get('delivery_pass'),'finished_with_answer':sr.get('finished_with_answer'),'grade_pass':g.get('pass'),'function_tests_passed':passed,'function_tests_total':total,'editorial_score':editorial(sr),'error':sr.get('error'),'reasoning_chars':sr.get('reasoning_chars'),'tool_calls':sr.get('tool_calls')}
def load_result(phase,profile,task,round_):
    p=S/'results'/phase/'short'/profile/'main/local'/(task+'-r'+str(round_))/'result.json'
    if not p.exists(): raise FileNotFoundError(p)
    d=read(p);return d
def load_long(profile,round_,stage=None):
    p=S/'results'/'validate'/'long'/profile/('r'+str(round_))/'record.json';return read(p)
def load_speed(profile,kind,round_):
    p=S/'results'/'screen'/'speed'/profile/(kind+'-r'+str(round_))/'result.json';d=read(p);resp=d.get('response') or {};t=resp.get('timings') or {};turn=[{'timings':t}];x={'source':p.relative_to(S).as_posix(),'elapsed_s':(d.get('latency') or {}).get('api_elapsed_s'),'api_wait_s':(d.get('latency') or {}).get('api_elapsed_s'),'observed_usage':resp.get('usage'),'usage':resp.get('usage'),'usage_complete':bool(resp.get('usage')),'native_speed':native(turn),'error':d.get('error'),'hard_pass':None,'delivery_pass':None,'grade':{},'reasoning_chars':0};return row_from_summary('screen',profile,'speed',kind,round_,x)
def main():
 dry='--dryrun' in __import__('sys').argv
 d=read(S/('summary-progress.json' if dry else 'summary.json'))
 if not dry: assert d.get('results_complete') is True and d.get('all_editorial_complete') is True,'final summary required'
 rows=[];missing=[]
 def add_short(phase,profile,task,r):
  sr=(d.get('phases',{}).get(phase,{}).get(profile,{}).get('short',{}).get(task,{}).get('rounds',[]))
  x=next((z for z in sr if z.get('round')==r),None)
  if x: rows.append(row_from_summary(phase,profile,'short',task,r,x))
  else: missing.append(f'{phase}/{profile}/{task}-r{r}')
 for phase,taskset in [('calibrate',['C03','A02','W03']),('validate',TASKS)]:
  for profile in d.get('phases',{}).get(phase,{}):
   for task in taskset:
    for r in (1,2): add_short(phase,profile,task,r)
 for profile in d.get('phases',{}).get('validate',{}):
  lg=d['phases']['validate'][profile].get('long',{})
  for group in ['episode','S1','S2','S3','S4']:
   for sr in lg.get(group,{}).get('rounds',[]):
    if group!='episode':
     ep=next(x for x in lg['episode']['rounds'] if x['round']==sr['round'])
     sr={**sr,'source':ep['source'],'usage_complete':all(counter((sr.get('usage') or {}).get(k)) for k in ['prompt_tokens','completion_tokens','total_tokens'])}
    rows.append(row_from_summary('validate',profile,'long_episode' if group=='episode' else 'long_stage',group,sr.get('round'),sr))
 # Speed screen rows retain raw JSON as source and native timing is calculated only here.
 screen=read(S/'screen-selection.json')
 for arm in screen.get('candidates',{}):
  profile=arm+'-medium'
  for kind in SPEED_KINDS:
   for r in (1,2):
    p=S/'results'/'screen'/'speed'/profile/(kind+'-r'+str(r))/'result.json'
    if p.exists(): rows.append(load_speed(profile,kind,r))
    else: missing.append(p.relative_to(S).as_posix())
 if not dry: assert len(rows)==76,(len(rows),missing,'expected 60 independent + 16 LH stages')
 fields=list(rows[0]) if rows else []
 if dry:
  checks={'rows_collected':len(rows),'missing':missing}
  w01=d.get('phases',{}).get('validate',{}).get('b0-medium',{}).get('short',{}).get('W01',{}).get('rounds',[])
  a02=d.get('phases',{}).get('calibrate',{}).get('b2-medium',{}).get('short',{}).get('A02',{}).get('rounds',[])
  s1=d.get('phases',{}).get('validate',{}).get('b0-medium',{}).get('long',{}).get('S1',{}).get('rounds',[])
  checks['W01_editorial_totals']=[(x.get('editorial') or {}).get('total') for x in w01]
  checks['A02_errors']=[x.get('error') for x in a02]
  checks['A02_grade_pass']=[(x.get('grade') or {}).get('pass') for x in a02]
  raw_lh=S/'results'/'validate'/'long'/'b0-medium'/'r1'/'record.json'
  if raw_lh.exists():
   rd=read(raw_lh); raw_s1=next((x for x in rd.get('stages',[]) if x.get('id')=='S1'),{})
   checks['long_S1_raw']={'error':raw_s1.get('error'),'grade_passed':(raw_s1.get('grade') or {}).get('passed'),'grade_total':(raw_s1.get('grade') or {}).get('total'),'calls':len(raw_s1.get('turns',[]))}
  else: checks['long_S1_raw']=None
  checks['speed_rows']=[x for x in rows if x['kind']=='speed']
  print(json.dumps({'dryrun':checks},ensure_ascii=False));return
 with (S/'measurements.csv').open('w',newline='',encoding='utf-8-sig') as f: w=csv.DictWriter(f,fieldnames=fields,lineterminator='\n');w.writeheader();w.writerows(rows)
 resources={}
 for phase in ('calibrate','validate','screen'):
  for kind in ('short','long','speed'):
   base=S/'results'/phase/kind
   if not base.exists():continue
   for profile in [p.name for p in base.iterdir() if p.is_dir()]:
    files=list((base/profile).rglob('resources.jsonl'));mem=[];gtt=[];samples=0
    for fp in files:
     for line in fp.read_text(encoding='utf-8').splitlines():
      try:q=json.loads(line)
      except ValueError:continue
      samples+=1
      if counter(q.get('MemAvailable')):mem.append(q['MemAvailable'])
      for g in q.get('gpu',[]):
       if isinstance(g,dict) and counter(g.get('GTT')):gtt.append(g['GTT'])
    resources.setdefault(profile,{})[phase+'/'+kind]={'minimum_MemAvailable_bytes':min(mem) if mem else None,'peak_GTT_bytes':max(gtt) if gtt else None,'samples':samples,'resource_files':len(files),'sampling_note':'resources.jsonl 2-second whole-system MemAvailable/GTT samples; formal phase only; missing remains null'}
 (S/'resource-summary.json').write_text(json.dumps({'profiles':resources,'source':'formal results/{screen,calibrate,validate}/**/resources.jsonl'},ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
 groups={'calibrate':{},'validate':{}}
 for phase in groups:
  for profile,p in d['phases'][phase].items():
   groups[phase][profile]={'short_workload':p.get('short_workload'),'short_expected':p.get('short_expected'),'short_delivery_count':p.get('short_delivery_count'),'short_delivery_pending':p.get('short_delivery_pending')}
 (S/'measurement-groups.json').write_text(json.dumps({'groups':groups,'screen':d.get('screen'),'note':'short_workload is phase/profile aggregation and is excluded from independent case rows','units':'seconds, tokens, tokens/second; null means unknown or not applicable'},ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
 print(json.dumps({'rows':len(rows),'independent':60,'lh_stage_derived':16,'profiles':sorted(resources)}))
if __name__=='__main__':main()
