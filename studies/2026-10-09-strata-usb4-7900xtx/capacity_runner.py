"""One capacity request per invocation; preserve first attempt including failure."""
import argparse,datetime,hashlib,json,os,time,urllib.request,urllib.error
from pathlib import Path
p=argparse.ArgumentParser()
p.add_argument('--study',type=Path,required=True);p.add_argument('--profile',required=True)
p.add_argument('--context',type=int,choices=[32768,65536,131072,262144,524288],required=True)
p.add_argument('--kind',choices=['retrieval','probe'],required=True)
p.add_argument('--context-slack8',action='store_true',help='explicit post-validation correction for524288 only; preserve original rejected attempt')
a=p.parse_args()
fixture=a.study/'capacity-fixtures'/f'{a.context}.json'
raw=fixture.read_bytes();case=json.loads(raw)
snapshot=json.loads((a.study/'environment'/f'{a.profile}.json').read_text(encoding='utf-8'))
tokenizer=snapshot['identity']['tokenizer_sha256']
assert all(tokenizer.get(k)==v for k,v in case['tokenizer_files_sha256'].items()),'freeze matching tokenizer fixtures before any capacity request'
if a.context_slack8:assert a.context==524288
suffix='-slack8' if a.context_slack8 else ''
f=a.study/'capacity'/a.profile/f'{a.context}-{a.kind}{suffix}.json'
if f.exists():raise SystemExit('never overwrite or auto retry')
messages=case['messages' if a.kind=='retrieval' else 'probe_messages']
payload={'model':os.environ['LOCAL_MODEL'],'messages':messages,'temperature':0,'enable_thinking':False,'reasoning_effort':'none','max_tokens':4096 if a.kind=='retrieval' else 512,'stream':False}
if a.context_slack8 and a.kind=='retrieval':payload['max_tokens']=min(4096,a.context-8-case['actual_retrieval_prompt_tokens'])
r={'profile':a.profile,'context_target':a.context,'kind':a.kind,'fixture_sha256':hashlib.sha256(raw).hexdigest(),'started_at':datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=8))).isoformat(),'parameters':{k:v for k,v in payload.items() if k!='messages'},'expected_prompt_tokens':case['actual_retrieval_prompt_tokens' if a.kind=='retrieval' else 'actual_probe_prompt_tokens']}
if a.context_slack8:r['capacity_validation_correction']='Explicit CTX_SLACK=8 reservation; same frozen input, no engine or sampling change; initial rejection retained separately'
start=time.monotonic()
try:
    req=urllib.request.Request(os.environ['LOCAL_BASE_URL'].rstrip('/')+'/chat/completions',data=json.dumps(payload,ensure_ascii=False).encode(),headers={'Authorization':'Bearer '+os.environ['LOCAL_API_KEY'],'Content-Type':'application/json'})
    with urllib.request.urlopen(req,timeout=1800) as resp:data=json.load(resp)
    r['response']=data
    text=data['choices'][0]['message'].get('content') or ''
    r['input_count_matches']=data.get('usage',{}).get('prompt_tokens')==r['expected_prompt_tokens']
    if not r['input_count_matches']:r['invalid_measurement']='API prompt token count differs from frozen tokenizer count'
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
except Exception as e:
    r.update(error=type(e).__name__,**{'pass':False})
    if isinstance(e,urllib.error.HTTPError):
        r['http_status']=e.code
        body=e.read(16384).decode('utf-8',errors='replace')
        try:r['error_body']=json.loads(body)
        except Exception:r['error_body']=body
r['elapsed_s']=time.monotonic()-start
f.parent.mkdir(parents=True,exist_ok=True);f.write_text(json.dumps(r,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
print(json.dumps({k:r[k] for k in ['profile','context_target','kind','pass','elapsed_s']},ensure_ascii=False),flush=True)
