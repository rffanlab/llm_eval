"""Append-only inputs; summarize native counters and editorial gates offline."""
import pathlib,json,hashlib,sys,statistics,importlib.util
S=pathlib.Path(__file__).resolve().parent
sys.path.insert(0,str(S));spec=importlib.util.spec_from_file_location('shared_metrics',S/'shared_metrics.py');m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);m.S=S
reviews=json.loads((S/'editorial-review.json').read_bytes())['reviews'] if (S/'editorial-review.json').exists() else {}
tasks=['D01','C01','W01','A01','C03','A02','W03'];missing=[]

def validation_profiles():
    """Read the explicit validation plan; never infer a complete plan from result folders."""
    plan=S/'validation-plan.json'
    if not plan.exists():
        missing.append(plan.relative_to(S).as_posix())
        return []
    value=json.loads(plan.read_bytes())
    raw=value.get('profiles',value) if isinstance(value,dict) else value
    names=[]
    for item in raw:
        name=item.get('profile') if isinstance(item,dict) else item
        if isinstance(name,str): names.append(name)
    return names
def load_short(phase,profile,task,rnd):
 p=S/'results'/phase/'short'/profile/'main/local'/(task+'-r'+str(rnd))/'result.json'
 if not p.exists():missing.append(p.relative_to(S).as_posix());return None
 d=json.loads(p.read_bytes());answer=(p.parent/'answer.txt').read_text(encoding='utf-8');assert answer==(d.get('content') or ''),'answer.txt differs from result content'
 editor=m.editor(p.parent/'answer.txt',answer,reviews) if task.startswith('W') else None
 hard=d.get('grade',{}).get('pass') is True and not d.get('error');delivery=hard and editor['pass'] if editor is not None else None if hard and task.startswith('W') else hard
 return {'round':rnd,'source':p.relative_to(S).as_posix(),'elapsed_s':d['elapsed_s'],'usage':m.usage(d),'observed_usage':d.get('usage'),'usage_complete':d.get('usage_complete'),'error':d.get('error'),'native_speed':m.speed(d.get('turns',[]),d.get('error')),'hard_pass':hard,'delivery_pass':delivery,'grade':d.get('grade'),'editorial':editor,'reasoning_chars':d.get('reasoning_chars'),'api_wait_s':sum(t.get('api_elapsed_s',0) for t in d['turns']),'tool_calls':len(d.get('tool_trace',[])),'resources':m.resources(p.parent),'first_content_call_s':[t.get('first_content_s') for t in d['turns']],'final_content_chars':len(answer),'raw_sha256':hashlib.sha256(p.read_bytes()).hexdigest()}
def load_long(profile,rnd):
 p=S/'results/validate/long'/profile/('r'+str(rnd))/'record.json'
 if not p.exists():missing.append(p.relative_to(S).as_posix());return None
 d=json.loads(p.read_bytes());stages=[];turns=[]
 for stage in d['stages']:
  ts=stage['turns'];turns+=ts;hard=stage.get('grade',{}).get('pass') is True and not stage.get('error')
  stages.append({'round':rnd,**{k:stage.get(k) for k in ['id','name','elapsed_s','error','finished_with_answer','grade']},'usage':m.total_usage(ts),'native_speed':m.speed(ts,stage.get('error')),'hard_pass':hard,'delivery_pass':hard and stage.get('finished_with_answer') is True,'calls':len(ts),'tool_calls':len(stage.get('tool_events',[])),'api_wait_s':sum(t.get('api_elapsed_s',0) for t in ts),'reasoning_chars':sum(t.get('reasoning_chars',0) for t in ts)})
 rp=p.parent/'workspace/delivery.md';answer=rp.read_text(encoding='utf-8') if rp.exists() else '';editor=m.editor(rp,answer,reviews)
 for stage in stages:
  if stage['id']=='S4':stage['editorial']=editor;stage['delivery_pass']=stage['delivery_pass'] and editor['pass'] if editor is not None else None if stage['delivery_pass'] else False
 hard=d.get('complete_delivery') is True and not d.get('error') and d.get('elapsed_s',2401)<=2400 and (m.usage(d) or {}).get('completion_tokens',65537)<=65536
 return {'round':rnd,'source':p.relative_to(S).as_posix(),'elapsed_s':d['elapsed_s'],'usage':m.usage(d),'observed_usage':d.get('usage'),'usage_complete':d.get('usage_complete'),'error':d.get('error'),'native_speed':m.speed(turns,d.get('error')),'hard_pass':hard,'delivery_pass':hard and editor['pass'] if editor is not None else None if hard else False,'editorial':editor,'stages':stages,'resources':m.resources(p.parent),'final_functional_pass':len(stages)==4 and stages[-1]['grade'].get('pass') is True}
validation=validation_profiles()
out={'phases':{'validate':{}},'missing':missing,'reviewer':'unblinded primary assistant; not owner approval','native_rate_rule':'sum native tokens / sum native seconds per round, then median; reused cache separate; missing stays unknown','frozen_sources_unchanged':all(hashlib.sha256((S/k).read_bytes()).hexdigest()==v for k,v in json.loads((S/'freeze.json').read_bytes())['files'].items())}
for profile in validation:
  taskset=tasks;pd={'short':{}}
  allrounds={1:[],2:[]}
  for task in taskset:
   rows=[r for rnd in [1,2] if (r:=load_short('validate',profile,task,rnd)) is not None];pd['short'][task]=m.summarize(rows)
   for row in rows:allrounds[row['round']].append(row)
  pd['short_delivery_count']=sum(x['delivery_pass_count'] for x in pd['short'].values());pd['short_delivery_pending']=sum(x['delivery_pending'] for x in pd['short'].values());pd['short_expected']=len(taskset)*2
  pd['short_elapsed_median_sum_s']=m.median([sum(r['elapsed_s'] for r in rows) if len(rows)==len(taskset) else None for rows in allrounds.values()])
  workloads=[]
  for rnd,rows in allrounds.items():
   if len(rows)!=len(taskset):continue
   ds=[json.loads((S/r['source']).read_bytes()) for r in rows];turns=[t for d in ds for t in d['turns']]
   known={'output_truncated','stage_call_budget','episode_wall_budget','episode_completion_budget','total_output_budget_exhausted','task_wall_budget','agent_reply_budget_exhausted'}
   uncertain=next((r['error'] for r in rows if r.get('error') and r['error'] not in known),None)
   workloads.append({'round':rnd,'elapsed_s':sum(r['elapsed_s'] for r in rows),'usage':m.total_usage(turns) if all(r['usage_complete'] for r in rows) else None,'native_speed':m.speed(turns,uncertain),'hard_pass':all(r['hard_pass'] for r in rows),'delivery_pass':None if any(r['delivery_pass'] is None for r in rows) else all(r['delivery_pass'] for r in rows),'tasks_delivered':sum(r['delivery_pass'] is True for r in rows),'tasks_total':len(rows),'reasoning_chars':sum(r['reasoning_chars'] for r in rows),'generated_tokens_observed':sum(r['native_speed']['decode_tokens_measured'] for r in rows)})
  pd['short_workload']=m.summarize(workloads)
  es=[e for rnd in [1,2] if (e:=load_long(profile,rnd)) is not None];pd['long']={'episode':m.summarize(es),'final_functional_pass_count':sum(e['final_functional_pass'] for e in es)}
  for sid in ['S1','S2','S3','S4']:pd['long'][sid]=m.summarize([x for e in es for x in e['stages'] if x['id']==sid])
  out['phases']['validate'][profile]=pd
writing_rows=[r for p in out['phases']['validate'].values() for task,data in p['short'].items() if task.startswith('W') for r in data['rounds']]
report_rows=[r for p in out['phases']['validate'].values() for r in p['long']['episode']['rounds']]
out['all_editorial_complete']=all(r.get('editorial') is not None for r in writing_rows+report_rows)
validation_complete=bool(validation) and all(sum(len(t['rounds']) for t in p['short'].values())==len(tasks)*2 and all(len(p['short'][task]['rounds'])==2 for task in tasks) and len(p['long']['episode']['rounds'])==2 and all(len(p['long'][sid]['rounds'])==2 for sid in ['S1','S2','S3','S4']) for p in out['phases']['validate'].values())
out['validation_complete']=validation_complete
out['results_complete']=not missing and validation_complete and out['all_editorial_complete']
dest=S/('summary.json' if '--final' in sys.argv else 'summary-progress.json')
if '--final' in sys.argv:assert out['results_complete'] and out['frozen_sources_unchanged']
dest.write_bytes((json.dumps(out,ensure_ascii=False,indent=2)+'\n').encode())
brief={p:{'short_rounds':sum(len(t['rounds']) for t in d['short'].values()),'long_rounds':len(d['long']['episode']['rounds'])} for p,d in out['phases']['validate'].items()}
print(json.dumps({'complete':out['results_complete'],'missing':len(missing),'validation':brief},ensure_ascii=False))
