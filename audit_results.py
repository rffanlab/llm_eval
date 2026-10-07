"""Offline evidence audit: hashes, response accounting, and semantic E01 view."""
import hashlib,json
from pathlib import Path
R=Path(__file__).resolve().parent
S=R/'studies/2026-10-07-local-vs-cloud'
def main():
    raw=(R/'suite/tasks.json').read_bytes()
    sha=hashlib.sha256(raw).hexdigest()
    rows=[]
    for path in sorted(list((S/'results').glob('*/result.json'))+list((S/'diagnostics').glob('*/*/result.json'))):
        d=json.loads(path.read_text(encoding='utf-8'))
        if 'grade' not in d:continue
        row={'attempt':path.parent.name,'fixture_matches':d['fixture_sha256']==sha,'answer_matches':(path.parent/'answer.txt').read_text(encoding='utf-8')==d['content'],'result_sha256':hashlib.sha256(path.read_bytes()).hexdigest(),'usage_complete':not bool(d.get('error'))}
        row['source']=path.relative_to(S).as_posix()
        row['usage_adds_up']=all(d['usage'][k]==sum(t['usage'][k] for t in d['turns']) for k in ['prompt_tokens','completion_tokens','total_tokens'])
        if d['task']=='E01':
            try:
                a=json.loads(d['content']);src=a.get('sources');src=[src.get(k) for k in ['owner','timeout_s','retry']] if isinstance(src,dict) else src
                row['semantic_values_and_sources_correct']=a.get('owner')=='周宁' and a.get('timeout_s')==45 and a.get('retry')==2 and src==['R071','R319','R447']
            except Exception:row['semantic_values_and_sources_correct']=False
        rows.append(row)
    out={'fixture_sha256':sha,'note':'Semantic E01 is supplementary; frozen strict grade remains unchanged. Missing timeout usage is unknown, not zero billed tokens.','records':rows}
    (S/'audit.json').write_text(json.dumps(out,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    assert all(x['fixture_matches'] and x['answer_matches'] and x['usage_adds_up'] for x in rows)
    print('AUDITED',len(rows))
if __name__=='__main__':main()
