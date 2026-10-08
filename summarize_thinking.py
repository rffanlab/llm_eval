import json,statistics
from pathlib import Path
S=Path(__file__).resolve().parent/'studies/2026-10-08-halogen-three-way'
profiles=['old-w4b','new-v2','swift-v2'];rows=[];total_known=0;unknown=0
for profile in profiles:
 for task in ['O01','O02','O03']:
  modes={}
  for mode in ['on','off']:
   ds=[json.loads(f.read_text(encoding='utf-8')) for f in sorted((S/'overthinking'/profile).glob(f'{task}-{mode}-r*.json'))]
   if not ds:continue
   valid=[d for d in ds if isinstance(d.get('response',{}).get('usage',{}).get('total_tokens'),int)]
   total_known+=sum(d['response']['usage']['total_tokens'] for d in valid);unknown+=len(ds)-len(valid)
   c=[d['response']['usage']['completion_tokens'] for d in valid];r=[d['response']['usage'].get('completion_tokens_details',{}).get('reasoning_tokens') for d in valid]
   modes[mode]={'n':len(ds),'passed':sum(d['pass'] for d in ds),'times_s':[d['elapsed_s'] for d in ds],'median_elapsed_s':statistics.median(d['elapsed_s'] for d in ds),'median_output_tokens':statistics.median(c) if c else None,'reasoning_tokens':r,'median_reasoning_tokens':statistics.median(r) if r and all(isinstance(x,int) for x in r) else None,'known_total_tokens':sum(d['response']['usage']['total_tokens'] for d in valid)}
  row={'profile':profile,'task':task,'modes':modes}
  if set(modes)=={'on','off'}:
   on,off=modes['on'],modes['off'];time_ratio=on['median_elapsed_s']/off['median_elapsed_s'];token_ratio=on['median_output_tokens']/off['median_output_tokens'] if off['median_output_tokens'] else None
   same_quality=on['passed']==off['passed']==on['n']==off['n']==2
   row.update(time_ratio=time_ratio,output_token_ratio=token_ratio,same_hard_quality=same_quality,registered_overthinking_flag=bool(same_quality and token_ratio is not None and token_ratio>=2 and time_ratio>=2 and on['median_reasoning_tokens'] is not None and on['median_reasoning_tokens']>=50 and on['median_elapsed_s']-off['median_elapsed_s']>=1))
  rows.append(row)
result={'status':'complete' if all(sum(x.get('modes',{}).get(m,{}).get('n',0) for x in rows)==18 for m in ['on','off']) else 'incomplete','known_total_tokens':total_known,'unknown_usage_n':unknown,'rows':rows,'definition':'overthinking-protocol.md; local task-specific operational threshold, not a claim about the entire Qwen family','complex_controls':{p:[json.loads(f.read_text(encoding='utf-8')) for f in (S/'thinking-complex'/p).glob('*/result.json')] for p in profiles}}
(S/'thinking-summary.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
print(json.dumps({'status':result['status'],'known_total_tokens':total_known,'completed_short_cases':sum(y['n'] for x in rows for y in x['modes'].values())},ensure_ascii=False))
