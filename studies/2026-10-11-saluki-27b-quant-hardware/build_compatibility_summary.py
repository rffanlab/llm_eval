"""Secondary, explicitly post hoc paragraph interpretation; originals stay untouched."""
import argparse,copy,hashlib,json,pathlib
from build_comparisons import build
S=pathlib.Path(__file__).resolve().parent
load=lambda p:json.loads(p.read_text(encoding='utf-8'))

def main(summary_path,compatibility_path,output,allow_partial=False):
    original=load(summary_path);interpretation=load(compatibility_path)
    assert interpretation['interpretation']==load(S/'paragraph-compatibility-registration.json')
    assert original['status']=='complete' or allow_partial
    derived=copy.deepcopy(original);rows=derived['record_rows'];changes=[];seen=set()
    for entry in interpretation['rows']:
        if entry['collection']!='main':continue
        row=next(x for x in rows if x['source']==entry['source'])
        assert entry['source'] not in seen;seen.add(entry['source'])
        assert row['case']=='W02' and row['hard_pass']==entry['original_hard_pass']
        answer=S/pathlib.Path(entry['source']).parent/'answer.txt'
        if 'answer_sha256' in entry:
            assert hashlib.sha256(answer.read_bytes()).hexdigest()==entry['answer_sha256']
            assert row['editor_score']==entry['editor_score']
        else:
            # Timed-out, empty records have no paragraph checks in the registered
            # interpreter. Retain their failure, verifying the actual empty body.
            assert entry.get('error') and row.get('error')==entry['error']
            assert answer.read_text(encoding='utf-8')=='' and row['body_chars']==0
            assert row['accepted'] is False and row['hard_pass'] is False
            assert entry['compatible_accepted'] is False and entry['compatible_hard_pass'] is False
            assert row['editor_score'] in (None,0)
        row['original_accepted']=row['accepted'];row['original_hard_pass']=row['hard_pass']
        row['original_outcome']=row['outcome']
        row['accepted']=entry['compatible_accepted'];row['hard_pass']=entry['compatible_hard_pass']
        if row['accepted'] is True:row['outcome']='accepted_under_secondary_paragraph_interpretation'
        if row['original_accepted']!=row['accepted']:changes.append({k:row[k] for k in ['source','original_accepted','accepted']})
    for name,profile in derived['profiles'].items():
        if profile['status']!='complete':continue
        main_rows=[x for x in rows if x['profile']==name and x['collection']=='main']
        assert len(main_rows)==18 and all(isinstance(x['accepted'],bool) for x in main_rows)
        assert next(x['source'] for x in main_rows if x['case']=='W02') in seen
        profile['original_accepted_sessions']=profile['accepted_sessions']
        profile['accepted_sessions']=sum(x['accepted'] for x in main_rows)
        profile['completion_rate']=profile['accepted_sessions']/18
    pairs=build(derived,load(S/'acceptance-gate.json'),allow_partial)
    document={'interpretation':interpretation['interpretation'],'not_primary_score':True,
              'source_summary_sha256':hashlib.sha256(summary_path.read_bytes()).hexdigest(),
              'source_compatibility_sha256':hashlib.sha256(compatibility_path.read_bytes()).hexdigest(),
              'status':original['status'],'changed_acceptances':changes,
              'secondary_profiles':derived['profiles'],'secondary_record_rows':rows,
              'secondary_comparisons':pairs['comparisons'],
              'reporting':'Original and secondary results must be shown separately. No original answer, review or raw score is changed.'}
    output.parent.mkdir(parents=True,exist_ok=True)
    output.write_text(json.dumps(document,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({'status':document['status'],'secondary_changed_acceptances':len(changes)}))

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--summary',type=pathlib.Path,required=True)
    p.add_argument('--compatibility',type=pathlib.Path,required=True)
    p.add_argument('--output',type=pathlib.Path,required=True);p.add_argument('--allow-partial',action='store_true')
    a=p.parse_args();main(a.summary.resolve(),a.compatibility.resolve(),a.output.resolve(),a.allow_partial)
