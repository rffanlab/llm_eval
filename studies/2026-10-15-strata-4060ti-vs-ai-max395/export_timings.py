"""Export recorded client/native timers; does not infer missing values."""
from pathlib import Path
import csv
import json

S=Path(__file__).resolve().parent
rows=[]

def add(profile,task,round_no,variant,stage,turn,source):
    u,t=turn.get('usage') or {},turn.get('timings') or {}
    rows.append(dict(profile=profile,task=task,round=round_no,variant=variant,stage=stage,
        turn=turn.get('index',1),source=source.as_posix(),finish_reason=turn.get('finish_reason'),
        api_elapsed_s=turn.get('api_elapsed_s'),first_event_s=turn.get('first_event_s'),
        first_reasoning_s=turn.get('first_reasoning_s'),first_content_s=turn.get('first_content_s'),
        first_tool_s=turn.get('first_tool_s'),prompt_tokens=u.get('prompt_tokens'),
        completion_tokens=u.get('completion_tokens'),total_tokens=u.get('total_tokens'),
        cached_tokens=(u.get('prompt_tokens_details') or {}).get('cached_tokens'),
        native_prompt_n=t.get('prompt_n'),native_cache_n=t.get('cache_n'),
        native_prompt_ms=t.get('prompt_ms'),native_prefill_tokens_s=t.get('prompt_per_second'),
        native_predicted_n=t.get('predicted_n'),native_decode_ms=t.get('predicted_ms'),
        native_decode_tokens_s=t.get('predicted_per_second'),draft_n=t.get('draft_n'),
        draft_n_accepted=t.get('draft_n_accepted'),reasoning_chars=turn.get('reasoning_chars')))

for p in sorted((S/'results/short').rglob('result.json')):
    r=json.loads(p.read_text(encoding='utf-8'))
    for t in r['turns']:add(r['profile'],r['task'],r['round'],r['variant'],'',t,p.relative_to(S))
for p in sorted((S/'results/long').rglob('record.json')):
    r=json.loads(p.read_text(encoding='utf-8'))
    for stage in r['stages']:
        for t in stage['turns']:add(r['profile'],'LH01',r['round'],'main',stage['id'],t,p.relative_to(S))
for p in sorted((S/'results/speed').rglob('result.json')):
    r=json.loads(p.read_text(encoding='utf-8'));response=r.get('response') or {}
    t=dict(r.get('latency') or {});t.update(usage=response.get('usage'),timings=response.get('timings'))
    add(r['profile'],'speed-'+r['kind'],r['round'],'unscored','',t,p.relative_to(S))
assert rows
with (S/'all-turn-timings.csv').open('w',encoding='utf-8',newline='') as f:
    writer=csv.DictWriter(f,fieldnames=list(rows[0]));writer.writeheader();writer.writerows(rows)
print('Exported',len(rows),'API calls; empty fields remain unknown')
