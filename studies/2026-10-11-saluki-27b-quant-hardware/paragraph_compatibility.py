"""Offline W02 paragraph interpretation; never modify original recordings."""
import argparse,hashlib,json,pathlib,re
S=pathlib.Path(__file__).resolve().parent
load=lambda p:json.loads(p.read_text(encoding='utf-8'))

def paragraph_blocks(text):
 text=text.replace('\r\n','\n').replace('\r','\n').strip()
 if not text:return []
 if re.search(r'\n[ \t]*\n',text):return [x.strip() for x in re.split(r'\n[ \t]*\n+',text) if x.strip()]
 return [x.strip() for x in text.splitlines() if x.strip()]

def main(output):
 registration=load(S/'paragraph-compatibility-registration.json')
 assert hashlib.sha256(pathlib.Path(__file__).read_bytes()).hexdigest()==registration['runner_sha256']
 for name,digest in load(S/'freeze.json')['hashes'].items():assert hashlib.sha256((S/name).read_bytes()).hexdigest()==digest
 reviews=load(S/'editor-reviews.json') if (S/'editor-reviews.json').exists() else []
 rows=[]
 for group in ['main','thinking-complex','native-sampling']:
  for path in sorted((S/group).glob('*/W02-r1/result.json')):
   r=load(path)
   if 'elapsed_s' not in r or 'grade' not in r:continue
   blocks=paragraph_blocks(r.get('content',''));old=r['grade'].get('checks')
   if not isinstance(old,dict):
    rows.append({'collection':group,'profile':r['profile'],'source':path.relative_to(S).as_posix(),'original_hard_pass':False,'compatible_hard_pass':False,'compatible_accepted':False,'error':r.get('error')});continue
   checks=dict(old);checks['paragraphs']=len(blocks)==3
   review=next((x for x in reviews if (x['collection'],x['profile'],x['task'])==(group,r['profile'],'W02')),None)
   if review:assert hashlib.sha256((path.parent/'answer.txt').read_bytes()).hexdigest()==review['answer_sha256']
   compatible=all(checks.values())
   rows.append({'collection':group,'profile':r['profile'],'source':path.relative_to(S).as_posix(),'answer_sha256':hashlib.sha256((path.parent/'answer.txt').read_bytes()).hexdigest(),'original_hard_pass':r['grade']['pass'],'original_checks':old,'compatible_paragraph_count':len(blocks),'compatible_checks':checks,'compatible_hard_pass':compatible,'editor_score':review['total'] if review else None,'compatible_accepted':bool(compatible and review['pass']) if review else None,'source_marker_in_each_paragraph':[any(m in x for m in ['[S1]','[S2]','[S3]']) for x in blocks],'original_records_edited':False})
 d={'interpretation':registration,'rows':rows}
 output.parent.mkdir(parents=True,exist_ok=True);output.write_text(json.dumps(d,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
 print(json.dumps({'rows':len(rows),'changed_hard_decisions':sum(x['original_hard_pass']!=x['compatible_hard_pass'] for x in rows)},ensure_ascii=False))

if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--output',type=pathlib.Path,required=True);a=p.parse_args();main(a.output.resolve())
