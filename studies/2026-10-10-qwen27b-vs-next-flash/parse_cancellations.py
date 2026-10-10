"""Keep cancelled server counters separate from missing terminal API usage."""
import csv,json,re
from pathlib import Path
S=Path(__file__).resolve().parent
text=(S/'environment/27b-ar-journal.txt').read_text(encoding='utf-8')
lines=[l for l in text.splitlines() if 'event=completed' in l and 'finish=cancelled' in l]
tasks=[]
for task in ['C03','W03']:
 r=json.loads((S/'ar-quality-controls/27b-ar'/f'{task}-local-r1/result.json').read_text(encoding='utf-8'))
 if 'Timeout' in (r.get('error') or ''):tasks.append(task)
assert len(lines)==len(tasks),(len(lines),tasks)
rows=[]
for task,line in zip(tasks,lines):
 fields=dict(re.findall(r'(\w+)=([^\s]+)',line))
 assert fields['path']=='/v1/chat/completions' and fields['finish']=='cancelled'
 rows.append({'task':task,'profile':'27b-ar','api_terminal_usage':None,'source':'environment/27b-ar-journal.txt',
  'request_id':fields['request'],'server_request_duration_ms':float(fields['duration_ms']),
  'prompt_tokens_server':int(fields['prompt_tokens']),'generated_tokens_at_cancel_server':int(fields['generated_tokens']),
  'new_prefill_tokens_server':int(fields['prefill_tokens']),'queue_ms_server':float(fields['queue_ms']),
  'ttft_ms_server':float(fields['ttft_ms']),'prefill_tps_server_rounded':float(fields['prefill_tps']),
  'decode_tps_server_rounded':float(fields['decode_tps']),'verbatim_server_line':line})
out={'rows':rows,'scope':'Server counters at request cancellation, ordered after six registered AR probes. Terminal API usage missing remains unknown. Rounded server rates do not justify reconstructing precise stage durations.',
 'native_cancelled_prompt_tokens':sum(x['prompt_tokens_server'] for x in rows),'native_cancelled_generated_tokens':sum(x['generated_tokens_at_cancel_server'] for x in rows)}
(S/'cancelled-server-counters.json').write_text(json.dumps(out,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
with (S/'cancelled-server-counters.csv').open('w',encoding='utf-8-sig',newline='') as f:
 if rows:
  w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)
print(json.dumps(out,ensure_ascii=False,indent=2))
