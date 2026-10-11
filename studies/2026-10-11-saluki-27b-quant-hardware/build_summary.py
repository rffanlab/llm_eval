"""Derive comparable measurements from terminal recordings and hash-bound reviews.

No inference, repairs, new scores, or replacement of first attempts occurs here.
Use --allow-partial only with a private output path while collection is running.
"""
import argparse,hashlib,json,pathlib,statistics
from inventory_results import ledger_row,result_files
S=pathlib.Path(__file__).resolve().parent
load=lambda p:json.loads(p.read_text(encoding='utf-8'))
median=lambda xs:statistics.median(xs) if xs else None

def expected_paths(profile,freeze):
 rows=[('main',case+'-r'+str(r)) for case,r in freeze['main_order']]
 rows += [('preflight',c+'-r1') for c in ['D01','O01']]
 rows += [('probe','code512-r'+str(r)) for r in [1,2,3]]
 rows += [('timing',c+'-'+repeat) for c in ['small','medium','large'] for repeat in ['new-prefix','exact-repeat']]
 rows += [('thinking',c+'-'+mode+'-r'+str(r)) for c in ['O01','O02','O03'] for mode in ['on','off'] for r in [1,2]]
 rows += [('thinking-complex',c+'-r1') for c in ['C03','C01','W01','W02','W03']]
 rows += [('native-sampling',c+'-r1') for c in ['C03','W02']]
 assert len(rows)==48
 return {group+'/'+profile+'/'+name+'/result.json' for group,name in rows}

def main(output,allow_partial=False):
 frozen=load(S/'freeze.json');models=load(S/'models.json');tasks=load(S/'tasks.json')['tasks']
 for name,digest in frozen['hashes'].items():assert hashlib.sha256((S/name).read_bytes()).hexdigest()==digest,name
 reviews=load(S/'editor-reviews.json') if (S/'editor-reviews.json').exists() else []
 review_map={}
 for x in reviews:
  key=(x['collection'],x['profile'],x['task']);assert key not in review_map,key
  answer=S/x['collection']/x['profile']/(x['task']+'-r1')/'answer.txt'
  assert hashlib.sha256(answer.read_bytes()).hexdigest()==x['answer_sha256'],key
  assert x['total']==sum(x['dimensions'].values()) and x['pass']==(x['total']>=16),key
  assert len(x['dimensions'])==4 and all(0<=v<=5 for v in x['dimensions'].values()),key
  review_map[key]=x
 rows=[];pending=[]
 for p in result_files(S):
  r=load(p);rel=p.relative_to(S).as_posix();group,profile,folder,_=rel.split('/')
  if 'elapsed_s' not in r or 'grade' not in r:pending.append(rel);continue
  assert r['profile']==profile and r['elapsed_s']>=0
  assert all(t.get('returned_model')==profile for t in r.get('turns',[])),rel
  assert (p.parent/'answer.txt').read_text(encoding='utf-8')==r.get('content',''),rel
  row=ledger_row(p,r);row.update(collection=group,folder=folder,source=rel,body_chars=len(''.join(r.get('content','').split())),finish_reason=r['turns'][-1].get('finish_reason') if r.get('turns') else None)
  row['accepted']=row['hard_pass'];row['editor_score']=None
  if r['grade'].get('editor_review_pending'):
   rev=review_map.get((group,profile,r['case']))
   if rev:
    assert rev['hard_rules_pass']==row['hard_pass'],rel
    row.update(editor_score=rev['total'],accepted=bool(row['hard_pass'] and rev['pass']),editor_review_pending=False)
   else:row.update(accepted=None,editor_review_pending=True)
  else:row['editor_review_pending']=False
  row['native_prefill_s']=row['native_prompt_ms']/1000 if row['native_prompt_ms'] is not None else None
  row['native_decode_s']=row['native_predicted_ms']/1000 if row['native_predicted_ms'] is not None else None
  cache_values=[t.get('timings',{}).get('cache_n') for t in r['turns'] if isinstance(t.get('timings'),dict)]
  row['native_cached_tokens']=sum(cache_values) if cache_values and len(cache_values)==len(r['turns']) and all(isinstance(v,int) for v in cache_values) else None
  row['first_sse_s']=r.get('first_sse_chunk_s');row['first_reasoning_s']=r.get('first_reasoning_delta_s')
  row['error_or_rule_detail']=r.get('error') or r['grade'].get('error')
  reason_values=[t.get('reasoning_chars') for t in r['turns']]
  row['reasoning_chars_sum']=sum(reason_values) if reason_values and all(isinstance(v,int) for v in reason_values) else None
  if row['accepted']:row['outcome']='accepted'
  elif r.get('error'):row['outcome']='timeout' if r['error'].startswith('TimeoutError') else 'recorded_error'
  elif row['body_chars']==0 and row['finish_reason']=='length':row['outcome']='budget_exhausted_without_final_body'
  elif r['grade'].get('editor_review_pending'):row['outcome']='writing_review_pending' if row['accepted'] is None else 'writing_rules_or_editorial_failure'
  else:row['outcome']='delivery_or_functional_failure'
  rows.append(row)
 profiles={};task_rows=[]
 for host in frozen['hosts_order']:
  for variant in frozen['profiles_order']:
   profile=host+'-'+variant;rs=[x for x in rows if x['profile']==profile]
   launch_path=S/'environment'/host/('launch-'+variant+'.json')
   launch=load(launch_path) if launch_path.exists() else None
   cap_path=S/'environment'/host/(variant+'-resource-limit.json')
   cap=load(cap_path) if cap_path.exists() else None
   skipped=bool(cap or (launch and launch.get('status')=='skipped_resource_limit'))
   missing=sorted(expected_paths(profile,frozen)-{x['source'] for x in rs})
   mains=[x for x in rs if x['collection']=='main'];unreviewed=[x['source'] for x in rs if x['accepted'] is None]
   complete=bool(launch and launch.get('status')=='ready' and not missing and not unreviewed and not skipped)
   state='skipped_resource_limit' if skipped else 'complete' if complete else 'incomplete'
   sampler=S/'environment'/host/(variant+'-resources.jsonl')
   samples=[json.loads(l) for l in sampler.read_text().splitlines()] if sampler.exists() else []
   allocations=[x['gpu'][0]['used_bytes'] if host=='rtx3090' else sum(g['GTT']+g['VRAM'] for g in x['gpu']) for x in samples]
   if complete:assert allocations and max(allocations)<=24*2**30,profile
   basic=['D01','C01','C02','A01','R01']
   basic_pass={c:next((x['accepted'] for x in mains if x['case']==c),None) for c in basic}
   known=[x for x in mains if x['total_tokens'] is not None]
   probes=[x for x in rs if x['collection']=='probe']
   profiles[profile]={'host':host,'variant':variant,'status':state,'terminal_records':len(rs),'missing_records':missing,'unreviewed_writing':unreviewed,'main_recorded':len(mains),'main_expected':18,'accepted_sessions':sum(x['accepted'] is True for x in mains) if complete else None,'completion_rate':sum(x['accepted'] is True for x in mains)/18 if complete else None,'basic_task_passes':basic_pass,'basic_all_pass':all(v is True for v in basic_pass.values()) if complete else None,'main_total_wait_s':sum(x['elapsed_s'] for x in mains) if len(mains)==18 else None,'known_main_total_tokens':sum(x['total_tokens'] for x in known) if known else None,'main_incomplete_usage':[x['source'] for x in mains if x['usage_complete'] is not True],'load_and_ready_s':launch.get('load_and_ready_s',launch.get('load_s')) if launch else None,'load_cache_controlled':False,'peak_runtime_gpu_allocation_bytes':max(allocations) if allocations else None,'minimum_runtime_memavailable_bytes':min(x['MemAvailable_bytes'] for x in samples) if samples else None,'resource_samples':len(samples),'fixed512_decode_median_tokens_per_s':median([x['native_predicted_per_second'] for x in probes if x['native_predicted_per_second'] is not None]),'fixed512_full_wait_median_s':median([x['elapsed_s'] for x in probes]),'launch_status':launch.get('status') if launch else None}
   for task in tasks:
    cases=[x for x in mains if x['case']==task['id']]
    task_rows.append({'profile':profile,'task':task['id'],'difficulty':task.get('level',task.get('difficulty')),'domain':task['domain'],'status':state,'rounds_recorded':len(cases),'rounds_expected':3 if task['id'] in ['C03','A02','E01'] else 1,'accepted_rounds':sum(x['accepted'] is True for x in cases) if complete else None,'wall_median_s':median([x['elapsed_s'] for x in cases]),'prefill_median_s':median([x['native_prefill_s'] for x in cases if x['native_prefill_s'] is not None]),'decode_median_s':median([x['native_decode_s'] for x in cases if x['native_decode_s'] is not None]),'prompt_tokens_median':median([x['prompt_tokens'] for x in cases if x['prompt_tokens'] is not None]),'output_tokens_median':median([x['completion_tokens'] for x in cases if x['completion_tokens'] is not None]),'total_tokens_median':median([x['total_tokens'] for x in cases if x['total_tokens'] is not None]),'all_api_usage_complete':bool(cases) and all(x['usage_complete'] for x in cases),'outcomes':[x['outcome'] for x in cases],'records':[x['source'] for x in cases]})
 closed=all(x['status'] in ['complete','skipped_resource_limit'] for x in profiles.values()) and not pending
 if not allow_partial:assert closed,{'incomplete_profiles':[p for p,x in profiles.items() if x['status']=='incomplete'],'pending':pending}
 document={'status':'complete' if closed else 'incomplete','frozen_study':frozen['study'],'record_count':len(rows),'in_progress_files':pending,'models':models,'profiles':profiles,'task_rows':task_rows,'record_rows':rows,'not_human_or_blind_review':True,'missing_usage_is_unknown':True,'native_timing_definition':'sum per-turn timings; Agent input counts include repeated contexts. Native prompt_n is actually processed tokens and excludes cached prefix tokens. API prompt_tokens is the full input count.','load_peak_excluded_from_runtime_peak':True,'first_attempts_preserved':True,'main_completion_definition':'Each of 18 sessions must satisfy hard rules and, for writing, a hash-bound editorial score >=16/20. Incomplete or resource-skipped deployments are never scored as zero.'}
 output.parent.mkdir(parents=True,exist_ok=True);output.write_text(json.dumps(document,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
 print(json.dumps({'status':document['status'],'record_count':len(rows),'profiles':{p:{k:x[k] for k in ['status','terminal_records','accepted_sessions']} for p,x in profiles.items()}},ensure_ascii=False))

if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--output',type=pathlib.Path,required=True);p.add_argument('--allow-partial',action='store_true');a=p.parse_args();main(a.output.resolve(),a.allow_partial)
