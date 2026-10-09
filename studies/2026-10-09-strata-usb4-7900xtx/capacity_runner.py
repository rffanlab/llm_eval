"""One capacity request per invocation; preserve first attempt including failure."""
import argparse,datetime,hashlib,json,os,time,urllib.request
from pathlib import Path
p=argparse.ArgumentParser()
p.add_argument('--study',type=Path,required=True);p.add_argument('--profile',required=True)
p.add_argument('--context',type=int,choices=[32768,65536,131072,262144,524288],required=True)
p.add_argument('--kind',choices=['retrieval','probe'],required=True)
a=p.parse_args()
fixture=a.study/'capacity-fixtures'/f'{a.context}.json'
raw=fixture.read_bytes();case=json.loads(raw)
f=a.study/'capacity'/a.profile/f'{a.context}-{a.kind}.json'
if f.exists():raise SystemExit('never overwrite or auto retry')
messages=case['messages' if a.kind=='retrieval' else 'probe_messages']
payload={'model':os.environ['LOCAL_MODEL'],'messages':messages,'temperature':0,'enable_thinking':False,'reasoning_effort':'none','max_tokens':4096 if a.kind=='retrieval' else 512,'stream':False}
r={'profile':a.profile,'context_target':a.context,'kind':a.kind,'fixture_sha256':hashlib.sha256(raw).hexdigest(),'started_at':datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=8))).isoformat(),'parameters':{k:v for k,v in payload.items() if k!='messages'},'expected_prompt_tokens':case['actual_retrieval_prompt_tokens' if a.kind=='retrieval' else 'actual_probe_prompt_tokens']}
start=time.monotonic()
try:
    req=urllib.request.Request(os.environ['LOCAL_BASE_URL'].rstrip('/')+'/chat/completions',data=json.dumps(payload,ensure_ascii=False).encode(),headers={'Authorization':'Bearer '+os.environ['LOCAL_API_KEY'],'Content-Type':'application/json'})
    with urllib.request.urlopen(req,timeout=1800) as resp:data=json.load(resp)
    r['response']=data
    text=data['choices'][0]['message'].get('content') or ''
    r['input_count_matches']=data.get('usage',{}).get('prompt_tokens')==r['expected_prompt_tokens']
    if a.kind=='retrieval':
        try:parsed=json.loads(text)
        except Exception:parsed=None
        r['strict_format_pass']=isinstance(parsed,dict) and set(parsed)==set(case['expected'])
        semantic=parsed
        if semantic is None and text.strip().startswith('```'):
            try:semantic=json.loads('\n'.join(text.strip().splitlines()[1:-1]))
            except Exception:pass
        r['semantic_checks']={k:isinstance(semantic,dict) and type(semantic.get(k)) is type(v) and semantic.get(k)==v for k,v in case['expected'].items()}
        r['pass']=r['input_count_matches'] and r['strict_format_pass'] and all(r['semantic_checks'].values())
    else:
        r['pass']=r['input_count_matches'] and data.get('usage',{}).get('completion_tokens')==512 and data.get('timings',{}).get('predicted_n')==512
except Exception as e:r.update(error=type(e).__name__,**{'pass':False})
r['elapsed_s']=time.monotonic()-start
f.parent.mkdir(parents=True,exist_ok=True);f.write_text(json.dumps(r,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
print(json.dumps({k:r[k] for k in ['profile','context_target','kind','pass','elapsed_s']},ensure_ascii=False),flush=True)
