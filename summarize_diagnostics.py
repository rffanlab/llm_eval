"""Separate post-hoc diagnostics from the frozen primary score table."""
import json
from pathlib import Path
S=Path(__file__).resolve().parent/'studies/2026-10-07-local-vs-cloud'
rows=[]
for f in sorted((S/'diagnostics').glob('*/*/result.json')):
    d=json.loads(f.read_text(encoding='utf-8'))
    if 'grade' not in d:continue
    rows.append({'diagnostic':f.parent.parent.name,'task':d['task'],'provider':d['provider'],'parameters':d['parameters'],'elapsed_s':d['elapsed_s'],'grade':d['grade'],'usage':d['usage'],'usage_complete':not bool(d.get('error')),'finish_reasons':[t['finish_reason'] for t in d['turns']],'source':str(f.relative_to(S)).replace('\\','/')})
out={'planned_sessions':8,'completed_sessions':len(rows),'known_total_tokens':sum(r['usage']['total_tokens'] for r in rows),'usage_incomplete_sessions':sum(not r['usage_complete'] for r in rows),'cases':rows,'note':'Post-hoc registered diagnostics, not replacement primary grades; budget semantics and sample limitations apply.'}
(S/'diagnostic-summary.json').write_text(json.dumps(out,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
print('DIAGNOSTIC_SESSIONS',len(rows),'KNOWN_TOKENS',out['known_total_tokens'])
