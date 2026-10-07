"""Summarize archived responses only; never sends a model request."""
import hashlib
import json
import statistics
from pathlib import Path

ROOT=Path(__file__).resolve().parent
STUDY=ROOT/'studies/2026-10-07-local-vs-cloud'
def main():
    suite=json.loads((ROOT/'suite/tasks.json').read_text(encoding='utf-8'))
    rows=[json.loads(x.read_text(encoding='utf-8')) for x in sorted((STUDY/'results').glob('*/result.json'))]
    rows=[r for r in rows if 'grade' in r]
    expected={(t['id'],p,r) for t in suite['tasks'] for p in ['local','official'] for r in (range(1,4) if t['id'] in suite['repeat_tasks'] else [1])}
    actual={(r['task'],r['provider'],r['round']) for r in rows}
    missing=sorted(expected-actual)
    cases=[]
    for task in suite['tasks']:
        item={'task':task['id'],'domain':task['domain'],'level':task['level']}
        for provider in ['local','official']:
            selected=[r for r in rows if r['task']==task['id'] and r['provider']==provider]
            if not selected:continue
            item[provider]={'runs':len(selected),'passes':sum(r.get('grade',{}).get('pass',False) for r in selected),
                'score_mean':round(statistics.mean(r.get('grade',{}).get('score',0) for r in selected),2),
                'elapsed_median_s':round(statistics.median(r['elapsed_s'] for r in selected),3),
                'elapsed_range_s':[min(r['elapsed_s'] for r in selected),max(r['elapsed_s'] for r in selected)],
                'input_tokens':sum(r['usage']['prompt_tokens'] for r in selected),'output_tokens':sum(r['usage']['completion_tokens'] for r in selected),
                'total_tokens':sum(r['usage']['total_tokens'] for r in selected),'usage_incomplete_sessions':sum(bool(r.get('error')) for r in selected),'completed_model_responses':sum(len(r['turns']) for r in selected),'model_calls':sum(len(r['turns'])+int(bool(r.get('error')) and not r.get('error','').startswith(('agent_turn_limit','task_output_budget_exhausted'))) for r in selected),
                'tool_calls':sum(len(r.get('tool_trace',[])) for r in selected),'human_corrections':sum(r['human_corrections'] for r in selected)}
        if all(p in item for p in ['local','official']):
            item['local_minus_official_score']=round(item['local']['score_mean']-item['official']['score_mean'],2)
            item['local_to_official_latency_ratio']=round(item['local']['elapsed_median_s']/item['official']['elapsed_median_s'],3)
        cases.append(item)
    summary={'status':'complete' if not missing else 'partial','expected_task_sessions':len(expected),'completed_task_sessions':len(rows),
        'missing':missing,'completed_model_responses':sum(len(r['turns']) for r in rows),'actual_model_calls':sum(len(r['turns'])+int(bool(r.get('error')) and not r.get('error','').startswith(('agent_turn_limit','task_output_budget_exhausted'))) for r in rows),'total_tokens':sum(r['usage']['total_tokens'] for r in rows),'usage_incomplete_sessions':sum(bool(r.get('error')) for r in rows),
        'cases':cases,'caveat':'Writing hard checks are not editorial scores. Repeated tasks are not independent task types. End-to-end time includes server and transport.'}
    (STUDY/'summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({'status':summary['status'],'sessions':len(rows),'calls':summary['actual_model_calls'],'tokens':summary['total_tokens']},ensure_ascii=False))

if __name__=='__main__':main()
