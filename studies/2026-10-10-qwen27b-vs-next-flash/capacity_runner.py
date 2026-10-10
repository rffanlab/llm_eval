"""Frozen identical-message capacity comparison; never overwrite first attempts."""
import argparse,datetime,hashlib,json,os,time,urllib.request,urllib.error
from pathlib import Path
p=argparse.ArgumentParser();p.add_argument('--study',type=Path,required=True);p.add_argument('--profile',required=True);p.add_argument('--context',type=int,choices=[32768,131072,262144],required=True);p.add_argument('--kind',choices=['retrieval','probe'],required=True);a=p.parse_args()
raw=(a.study/'capacity-fixtures'/f'{a.context}.json').read_bytes();case=json.loads(raw)
freeze=json.loads((a.study/'capacity-freeze.json').read_text());assert hashlib.sha256(raw).hexdigest()==freeze['fixtures'][str(a.context)]
f=a.study/'capacity'/a.profile/f'{a.context}-{a.kind}.json';assert not f.exists(),'never overwrite or automatically retry'
payload={'model':os.environ['LOCAL_MODEL'],'messages':case['messages' if a.kind=='retrieval' else 'probe_messages'],'temperature':0,'presence_penalty':0,'reasoning_effort':'none','chat_template_kwargs':{'enable_thinking':False,'reasoning_effort':'none','preserve_thinking':False},'max_tokens':4096 if a.kind=='retrieval' else 512,'stream':False}
r={'profile':a.profile,'context_target':a.context,'service_context':262144,'kind':a.kind,'fixture_sha256':hashlib.sha256(raw).hexdigest(),'started_at':datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=8))).isoformat(),'parameters':{k:v for k,v in payload.items() if k!='messages'},'canonical_template_prompt_tokens':case['actual_retrieval_prompt_tokens' if a.kind=='retrieval' else 'actual_probe_prompt_tokens']}
start=time.monotonic()
try:
 req=urllib.request.Request(os.environ['LOCAL_BASE_URL'].rstrip('/')+'/chat/completions',data=json.dumps(payload,ensure_ascii=False).encode(),headers={'Authorization':'Bearer '+os.environ['LOCAL_API_KEY'],'Content-Type':'application/json'})
 with urllib.request.urlopen(req,timeout=1800) as resp:data=json.load(resp)
 r['response']=data;text=data['choices'][0]['message'].get('content') or '';count=data.get('usage',{}).get('prompt_tokens');r['actual_prompt_tokens']=count;r['canonical_count_matches']=count==r['canonical_template_prompt_tokens'];r['capacity_count_valid']=isinstance(count,int) and count>0 and count+payload['max_tokens']<=262144
 if a.kind=='retrieval':
  try:parsed=json.loads(text)
  except (ValueError,TypeError):parsed=None
  r['strict_format_pass']=isinstance(parsed,dict) and set(parsed)==set(case['expected']);r['semantic_checks']={k:isinstance(parsed,dict) and type(parsed.get(k)) is type(v) and parsed.get(k)==v for k,v in case['expected'].items()};r['pass']=r['capacity_count_valid'] and r['strict_format_pass'] and all(r['semantic_checks'].values())
 else:
  r['full_512_output']=data.get('usage',{}).get('completion_tokens')==512;r['pass']=r['capacity_count_valid'] and r['full_512_output']
except Exception as e:
 r.update(error=type(e).__name__,**{'pass':False})
 if isinstance(e,urllib.error.HTTPError):
  r['http_status']=e.code;body=e.read(16384).decode('utf-8',errors='replace')
  try:r['error_body']=json.loads(body)
  except ValueError:r['error_body']=body
r['elapsed_s']=time.monotonic()-start;f.parent.mkdir(parents=True,exist_ok=True);f.write_text(json.dumps(r,ensure_ascii=False,indent=2)+'\n',encoding='utf-8');print(json.dumps({k:r.get(k) for k in ['profile','context_target','kind','pass','actual_prompt_tokens','elapsed_s','error']},ensure_ascii=False),flush=True)
