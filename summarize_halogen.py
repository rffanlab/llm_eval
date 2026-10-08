"""Summarize the registered local engine/model comparison without filling missing runs."""
import json,statistics,hashlib
from pathlib import Path
ROOT=Path(__file__).resolve().parent;S=ROOT/'studies/2026-10-08-halogen-three-way'
profiles=['old-w4b','new-v2','swift-v2'];tasks=json.loads((S/'tasks.json').read_text(encoding='utf-8'))['tasks']
adjudications=json.loads((S/'adjudications.json').read_text(encoding='utf-8'))['entries'] if (S/'adjudications.json').exists() else []
def accepted(file,record):
 for a in adjudications:
  if (a['profile'],a['task'],a['round'])==(record['profile'],record['task'],record['round']):
   assert a['answer_sha256']==hashlib.sha256((file.parent/'answer.txt').read_bytes()).hexdigest()
   assert a['fixture_sha256']==record['fixture_sha256']
   return a['acceptance_pass']
 return record['grade']['pass']
rows=[]
for profile in profiles+['new-w4b-control']:
 for task in tasks:
  files=sorted((S/'results'/profile).glob(task['id']+'-local-r*/result.json'))
  if not files:continue
  ds=[json.loads(f.read_text(encoding='utf-8')) for f in files]
  rows.append({'profile':profile,'task':task['id'],'domain':task['domain'],'n':len(ds),'passed':sum(x['grade']['pass'] for x in ds),'scores':[x['grade']['score'] for x in ds],'elapsed_s':[x['elapsed_s'] for x in ds],'median_elapsed_s':statistics.median(x['elapsed_s'] for x in ds),'known_input_tokens':sum(x['usage']['prompt_tokens'] for x in ds),'known_output_tokens':sum(x['usage']['completion_tokens'] for x in ds),'known_total_tokens':sum(x['usage']['total_tokens'] for x in ds),'unknown_usage_n':sum(not x['usage_complete'] for x in ds),'reasoning_tokens':[(sum(t['usage']['completion_tokens_details']['reasoning_tokens'] for t in x['turns']) if all(isinstance(t['usage'].get('completion_tokens_details',{}).get('reasoning_tokens'),int) for t in x['turns']) else None) for x in ds],'finish_reasons':[[t['finish_reason'] for t in x['turns']] for x in ds],'server_decode_tps':[t['timings'].get('predicted_per_second') for x in ds for t in x['turns'] if t.get('timings')],'server_cache_tokens':[sum(t['timings'].get('cache_n',0) for t in x['turns'] if t.get('timings')) for x in ds]})
totals={p:{'sessions':sum(x['n'] for x in rows if x['profile']==p),'hard_passes':sum(x['passed'] for x in rows if x['profile']==p),'known_total_tokens':sum(x['known_total_tokens'] for x in rows if x['profile']==p),'known_output_tokens':sum(x['known_output_tokens'] for x in rows if x['profile']==p),'unknown_usage_sessions':sum(x['unknown_usage_n'] for x in rows if x['profile']==p)} for p in profiles}
complete=all(x['sessions']==16 for x in totals.values())
data={'status':'complete' if complete else 'incomplete','primary_profiles':profiles,'registered_primary_sessions':48,'completed_primary_sessions':sum(x['sessions'] for x in totals.values()),'totals':totals,'tasks':rows,'speed_probes':{p:[json.loads(f.read_text(encoding='utf-8')) for f in sorted((S/'speed-probes'/p).glob('*.json'))] for p in profiles},'observations':'See observations.md; raw trial timing and incidents are preserved. Writing editorial scores are separate.'}
for row in rows:
 files=sorted((S/'results'/row['profile']).glob(row['task']+'-local-r*/result.json'))
 ds=[json.loads(f.read_text(encoding='utf-8')) for f in files]
 row['raw_passed']=row['passed'];row['passed']=sum(accepted(f,d) for f,d in zip(files,ds))
for profile,total in totals.items():
 total['raw_hard_passes']=total['hard_passes'];total['hard_passes']=sum(x['passed'] for x in rows if x['profile']==profile)
data['adjudications']='adjudications.json; raw records and raw_passed remain unchanged'
(S/'summary.json').write_text(json.dumps(data,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
print(json.dumps({'status':data['status'],'totals':totals},ensure_ascii=False))
