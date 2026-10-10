"""Derive all recorded waits, native stages, tokens and outcomes without filling unknowns."""
import argparse,hashlib,json,statistics
from pathlib import Path
HERE=Path(__file__).resolve().parent
PROFILES=['next-flash-mtp','27b-dflash2']
def load(p):return json.loads(p.read_text(encoding='utf-8'))
def median(values):return statistics.median(values) if values else None
def total(values):return sum(values) if values and all(isinstance(x,(int,float)) for x in values) else None
def stages(usage,timings=None):
 n=(usage or {}).get('gufo') or {};t=timings or {}
 return {'queue_s':n.get('queue_ms')/1000 if n.get('queue_ms') is not None else None,
  'prefill_s':(n.get('prefill_ms',t.get('prompt_ms')))/1000 if n.get('prefill_ms',t.get('prompt_ms')) is not None else None,
  'decode_s':(n.get('decode_ms',t.get('predicted_ms')))/1000 if n.get('decode_ms',t.get('predicted_ms')) is not None else None,
  'server_ttft_s':n.get('ttft_ms')/1000 if n.get('ttft_ms') is not None else None,
  'new_prefill_tokens':n.get('prefill_tokens'),'cache_tokens':(usage or {}).get('cached_tokens',(usage or {}).get('prompt_tokens_details',{}).get('cached_tokens',t.get('cache_n'))),
  'cache_hit':n.get('cache_hit'),'cache_restore_ms':n.get('cache_restore_ms',t.get('cache_restore_ms')),
  'cache_snapshot_ms':n.get('cache_snapshot_ms',t.get('cache_snapshot_ms')),
  'draft_tokens':(usage or {}).get('draft_tokens',t.get('draft_n')),'draft_tokens_accepted':(usage or {}).get('draft_tokens_accepted',t.get('draft_n_accepted')),
  'reasoning_tokens':(usage or {}).get('completion_tokens_details',{}).get('reasoning_tokens')}
def main_row(path,task,editor):
 r=load(path);turns=[{'index':t['index'],'api_elapsed_s':t['elapsed_s'],'usage':t['usage'],**stages(t['usage'],t.get('timings'))} for t in r.get('turns',[])]
 score=editor.get((r['profile'],r['task']),{}).get('scores',{}).get('total')
 limit=60 if r['task'] in ['D01','C01','W01','C02','A01'] else 240
 mechanical=bool(r.get('grade',{}).get('pass'));accepted=mechanical and r['elapsed_s']<=limit and (score is not None and score>=16 if task['domain']=='writing' else True)
 if task['domain']=='writing' and score is None:accepted=None
 return {'source':path.relative_to(HERE).as_posix(),'profile':r['profile'],'task':r['task'],'round':r['round'],'domain':task['domain'],'difficulty':task.get('level'),
  'api_session_wait_s':r['elapsed_s'],'registered_limit_s':limit,'within_deadline':r['elapsed_s']<=limit,'mechanical_pass':mechanical,'editor_score':score,'accepted':accepted,
  'usage':r['usage'] if turns or r.get('usage_complete') else None,'usage_complete':r.get('usage_complete',False),'error':r.get('error'),'grade':r['grade'],'turns':turns,
  'prefill_s_sum':total([t['prefill_s'] for t in turns]),'decode_s_sum':total([t['decode_s'] for t in turns]),'queue_s_sum':total([t['queue_s'] for t in turns]),
  'server_ttft_s_per_turn':[t['server_ttft_s'] for t in turns],
  'answer_sha256':hashlib.sha256(path.with_name('answer.txt').read_bytes()).hexdigest()}
def control_row(path):
 r=load(path);response=r.get('response') or {};usage=r.get('usage') or response.get('usage')
 return {'source':path.relative_to(HERE).as_posix(),'profile':r['profile'],'kind':r.get('kind',path.parent.parent.name),'task':r.get('task'),'round':r.get('round'),
  'thinking':r.get('thinking'),'context_target':r.get('context_target'),'fixture':r.get('fixture'),'repeat':r.get('repeat'),
  'elapsed_s':r['elapsed_s'],'usage':usage,'error':r.get('error'),'pass':r.get('pass'),'full_512_output':r.get('full_512_output',r.get('full_512_output')),
  'client_first_sse_chunk_s':r.get('first_sse_chunk_s'),'client_first_nonempty_delta_s':r.get('first_nonempty_delta_s'),
  'client_first_reasoning_delta_s':r.get('first_reasoning_delta_s'),'client_first_content_delta_s':r.get('first_content_delta_s'),
  **stages(usage,response.get('timings'))}
def main():
 parser=argparse.ArgumentParser();parser.add_argument('--partial',action='store_true');args=parser.parse_args()
 frozen=load(HERE/'freeze.json');tasks={x['id']:x for x in load(HERE/'tasks.json')['tasks']}
 reviews=load(HERE/'editor-review.json') if (HERE/'editor-review.json').exists() else {'entries':[]}
 editors={(x['profile'],x['task']):x for x in reviews['entries']}
 rows=[];ledger=[];counts={}
 for group in ['results','preflight','thinking-complex','ar-quality-controls']:
  for path in sorted((HERE/group).rglob('result.json')):
   r=load(path);row=main_row(path,tasks[r['task']],editors);row['group']=group;rows.append(row)
   ledger.append({'source':row['source'],'profile':row['profile'],'group':group,'known_usage':row['usage'],'usage_complete':row['usage_complete'],'included_in_paired_main':group=='results'})
 for path in sorted((HERE/'diagnostics/writing-mode/records').rglob('result.json')):
  r=load(path);row=main_row(path,tasks[r['task']],editors);row['group']='writing-mode-diagnostic';rows.append(row)
  ledger.append({'source':row['source'],'profile':row['profile'],'group':row['group'],'known_usage':row['usage'],'usage_complete':row['usage_complete'],'included_in_paired_main':False})
 controls=[]
 for group in ['preflight-probes','speed-probes','repetition-probes','timing-probes','overthinking-native','capacity']:
  for path in sorted((HERE/group).rglob('*.json')):
   row=control_row(path);row['group']=group;controls.append(row)
   ledger.append({'source':row['source'],'profile':row['profile'],'group':group,'known_usage':row['usage'],'usage_complete':isinstance(row['usage'],dict) and not row['error'],'included_in_paired_main':False})
 for entry in ledger:
  bucket=counts.setdefault(entry['profile'],{});bucket[entry['group']]=bucket.get(entry['group'],0)+1
 totals={};bytask={}
 for profile in PROFILES:
  mainrows=[r for r in rows if r['profile']==profile and r['group']=='results'];writing=[r for r in mainrows if r['domain']=='writing']
  totals[profile]={'main_recordings':len(mainrows),'mechanical_pass':sum(r['mechanical_pass'] for r in mainrows),'accepted':sum(r['accepted'] is True for r in mainrows),
   'editor_review_complete':len(writing)==3 and all(r['editor_score'] is not None for r in writing),
   'api_session_wait_sum_s':sum(r['api_session_wait_s'] for r in mainrows),
   'native_prefill_sum_s':total([r['prefill_s_sum'] for r in mainrows]),'native_decode_sum_s':total([r['decode_s_sum'] for r in mainrows]),
   'known_tokens':{k:sum(r['usage'][k] for r in mainrows) for k in ['prompt_tokens','completion_tokens','total_tokens']},
   'unknown_usage_recordings':sum(not r['usage_complete'] for r in mainrows),
   'writing_editor_mean':statistics.mean([r['editor_score'] for r in writing]) if writing and all(r['editor_score'] is not None for r in writing) else None}
  for task in tasks:
   matches=[r for r in mainrows if r['task']==task]
   bytask.setdefault(task,{})[profile]={'n':len(matches),'rows':matches,'api_wait_median_s':median([r['api_session_wait_s'] for r in matches]),
    'prefill_median_s':median([r['prefill_s_sum'] for r in matches if r['prefill_s_sum'] is not None]),
    'decode_median_s':median([r['decode_s_sum'] for r in matches if r['decode_s_sum'] is not None])}
 core=[x for x in ledger if x['group']!='writing-mode-diagnostic']
 diagnostic=[r for r in rows if r['group']=='writing-mode-diagnostic']
 complete=len(core)==106 and len(diagnostic)==1 and diagnostic[0]['editor_score'] is not None and all(totals[p]['main_recordings']==16 and totals[p]['editor_review_complete'] for p in PROFILES)
 out={'status':'measurements_and_editor_review_complete' if complete else 'partial_do_not_publish_as_final','counts':counts,'main_totals':totals,'tasks':bytask,'control_rows':controls,
  'ledger':ledger,'diagnostic_rows':diagnostic,'recorded_measurements':len(ledger),'known_total_tokens_all_recordings':sum((x['known_usage'] or {}).get('total_tokens',0) for x in ledger),
  'unknown_usage_recordings':sum(not x['usage_complete'] for x in ledger),
  'timing_note':'Native stages may include nested work. TTFT per turn is not a single Agent session first-word wait; absent details remain unknown.'}
 if not args.partial:assert complete,'All106 core recordings, registered W01 diagnostic and writing reviews required; use --partial for progress'
 file=HERE/('running-summary.json' if args.partial else 'summary.json')
 file.write_text(json.dumps(out,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
 print(json.dumps({'status':out['status'],'recordings':len(ledger),'totals':totals},ensure_ascii=False,indent=2))
if __name__=='__main__':main()
