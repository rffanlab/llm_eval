"""Verify frozen inputs and serial deployment, then export every recorded timing."""
import csv,hashlib,json,re
from pathlib import Path
HERE=Path(__file__).resolve().parent;REPO=HERE.parents[1]
def load(p):return json.loads(p.read_text(encoding='utf-8'))
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def write_csv(name,rows):
 keys=list(dict.fromkeys(k for row in rows for k in row))
 with (HERE/name).open('w',encoding='utf-8-sig',newline='') as f:
  w=csv.DictWriter(f,fieldnames=keys);w.writeheader();w.writerows(rows)
frozen=load(HERE/'freeze.json');d=load(HERE/'summary.json');assert d['status']=='measurements_and_editor_review_complete'
findings=[];hashes={}
for base,mapping in [(HERE,frozen['files']),(REPO,frozen['runner_sha256'])]:
 for name,expected in mapping.items():
  actual=sha(base/name);hashes[name]=actual
  if actual!=expected:findings.append('frozen SHA mismatch: '+name)
review=load(HERE/'editor-review.json')
for x in review['entries']:
 if sha(HERE/x['source'])!=x['answer_sha256']:findings.append('editor source SHA mismatch: '+x['source'])
main=[];turns=[]
for x in d['ledger']:
 path=HERE/x['source'];hashes[x['source']]=sha(path)
 if path.name!='result.json':continue
 r=load(path)
 if r['fixture_sha256']!=frozen['files']['tasks.json']:findings.append('task fixture changed: '+x['source'])
 if path.with_name('answer.txt').read_text(encoding='utf-8')!=r['content']:findings.append('answer mismatch: '+x['source'])
 if x['included_in_paired_main']:
  p=r['parameters'];template=p['chat_template_kwargs']
  assert p['temperature']==0 and p['presence_penalty']==0 and p['enable_thinking'] and template['reasoning_effort']=='medium' and not template['preserve_thinking']
  main.append({'source':x['source'],'profile':r['profile'],'task':r['task'],'round':r['round'],'api_session_wait_s':r['elapsed_s'],
   **r['usage'],'usage_complete':r['usage_complete'],'mechanical_pass':r['grade']['pass'],'finish_reason':r['turns'][-1]['finish_reason'],'final_nonspace_chars':len(re.sub(r'\s','',r['content']))})
 for t in r['turns']:
  u=t['usage'];g=(u or {}).get('gufo') or {}
  turns.append({'source':x['source'],'profile':r['profile'],'group':x['group'],'task':r['task'],'round':r['round'],'turn':t['index'],'api_turn_wait_s':t['elapsed_s'],
   **{k:(u or {}).get(k) for k in ['prompt_tokens','completion_tokens','total_tokens','cached_tokens','draft_tokens','draft_tokens_accepted']},
   **{k:g.get(k) for k in ['queue_ms','prefill_ms','decode_ms','ttft_ms','prefill_tokens','cache_hit','cache_restore_ms','cache_snapshot_ms']},
   'decode_tokens_per_s':(u or {}).get('completion_tokens')/(g['decode_ms']/1000) if g.get('decode_ms') else None,
   'new_prefill_tokens_per_s':g.get('prefill_tokens')/(g['prefill_ms']/1000) if g.get('prefill_ms') else None,
   'reasoning_tokens':(u or {}).get('completion_tokens_details',{}).get('reasoning_tokens'),'finish_reason':t['finish_reason']})
write_csv('main-all-rounds.csv',main);write_csv('all-main-and-control-turn-timings.csv',turns)
controls=[]
for x in d['control_rows']:
 controls.append({k:v for k,v in x.items() if k!='usage'}|{k:(x['usage'] or {}).get(k) for k in ['prompt_tokens','completion_tokens','total_tokens']}|
  {'decode_tokens_per_s':(x['usage'] or {}).get('completion_tokens')/x['decode_s'] if x['decode_s'] else None,
   'new_prefill_tokens_per_s':x['new_prefill_tokens']/x['prefill_s'] if x['prefill_s'] and x['new_prefill_tokens'] is not None else None})
write_csv('all-native-and-stream-controls.csv',controls)
admissions=[json.loads(l) for l in (HERE/'diagnostics/single-model-admission.jsonl').read_text().splitlines() if l.strip()]
bootids=set();resources={};launches={}
for a in admissions:
 bootids.add(a['boot_id'])
 expected_model='Qwen/Qwen3.8-Flash-Next' if a['profile']=='next-flash-mtp' else 'Qwen/Qwen3.8-27B'
 if len(a['processes'])!=1 or not a['processes'][0]['owned_binary'] or a['processes'][0]['model_id']!=expected_model or a['MemAvailable_bytes']<8*2**30 or a['open_model_tcp_connections']!=0:findings.append('request admission failure')
for profile in ['next-flash-mtp','27b-dflash2','27b-ar']:
 launch=load(HERE/'environment'/f'{profile}-launch.json');stop=load(HERE/'environment'/f'{profile}-stop.json');launches[profile]=launch['load_and_ready_s']
 for state in [launch['before'],stop]:
  bootids.add(state['boot_id'])
  if state['processes'] or state['MemAvailable_bytes']<100*2**30 or any(g['VRAM']>=2*2**30 or g['GTT']>=4*2**30 for g in state['gpu']):findings.append('deployment release gate failed: '+profile)
 samples=[json.loads(l) for l in (HERE/'resources'/f'{profile}-resources.jsonl').read_text().splitlines() if l.strip()]
 for a in samples:
  bootids.add(a['boot_id'])
  if len(a['models'])>1:findings.append('simultaneous model sample: '+profile)
 kernels=(HERE/'environment'/f'{profile}-kernel.txt').read_text(encoding='utf-8')
 faults=[l for l in kernels.splitlines() if re.search(r'out of memory|oom-kill|GPU reset|GPU fault|ring .*timeout|recovery failed',l,re.I)]
 resources[profile]={'samples':len(samples),'min_MemAvailable_bytes':min(a['MemAvailable'] for a in samples),
  'max_APU_GTT_bytes':max(g['GTT'] for a in samples for g in a['GPUs'] if g['pci']=='0000:c5:00.0'),
  'max_APU_VRAM_bytes':max(g['VRAM'] for a in samples for g in a['GPUs'] if g['pci']=='0000:c5:00.0'),
  'kernel_fault_lines':faults,'sampled_model_process_count_max':max(len(a['models']) for a in samples)}
if len(bootids)!=1:findings.append('boot changed during measurement')
restored=load(HERE/'environment/restore.json');assert restored['production_service']==restored['router_service']=='active'
assert len(restored['processes'])==1 and restored['processes'][0]['model_id']=='Qwen/Qwen3.8-Flash-Next'
assert load(HERE/'environment/production-health.json')['pass']
equivalence=[]
for group in ['speed-probes','repetition-probes']:
 for round_ in [1,2,3]:
  left=HERE/group/'27b-ar'/f'r{round_}.json';right=HERE/group/'27b-dflash2'/f'r{round_}.json'
  c1=load(left)['response']['choices'][0]['message']['content'];c2=load(right)['response']['choices'][0]['message']['content']
  equivalence.append({'group':group,'round':round_,'ar_source':left.relative_to(HERE).as_posix(),'dflash_source':right.relative_to(HERE).as_posix(),'exact_answer_match':c1==c2,'answer_utf8_sha256':hashlib.sha256(c1.encode()).hexdigest()})
assert all(x['exact_answer_match'] for x in equivalence)
(HERE/'speed-output-equivalence.json').write_text(json.dumps(equivalence,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
cancelled=load(HERE/'cancelled-server-counters.json')
assert len(main)==32 and len(d['ledger'])==107
out={'status':'complete' if not findings else 'findings','integrity_findings':findings,'recorded_measurements':107,'paired_main_measurements':32,
 'core_measurements':106,'separately_registered_diagnostic_measurements':1,'request_admissions':len(admissions),'same_boot':len(bootids)==1,
 'resources':resources,'load_to_authenticated_ready_s':launches,'filesystem_cache_controlled':False,
 'known_total_tokens_all_recordings':d['known_total_tokens_all_recordings'],'unknown_usage_recordings':d['unknown_usage_recordings'],
 'native_cancelled_prompt_tokens':cancelled['native_cancelled_prompt_tokens'],'native_cancelled_generated_tokens':cancelled['native_cancelled_generated_tokens'],
 'api_known_plus_cancelled_server_token_counters':d['known_total_tokens_all_recordings']+cancelled['native_cancelled_prompt_tokens']+cancelled['native_cancelled_generated_tokens'],
 'fixed_probe_answers_equal_to_ar':all(x['exact_answer_match'] for x in equivalence),
 'known_total_tokens_paired_main':sum(x['total_tokens'] for x in main),'source_sha256':hashes,
 'production_restored':'Next Flash and router active; no automatic adoption of27B','review_boundary':'Visible-identity primary editorial review; owner listening and approval separate'}
(HERE/'audit.json').write_text(json.dumps(out,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
assert not findings,findings
print(json.dumps({k:v for k,v in out.items() if k not in ['resources','source_sha256']},ensure_ascii=False,indent=2))
