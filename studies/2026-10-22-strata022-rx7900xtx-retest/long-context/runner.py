"""Exactly one long-context comprehension case, explicitly initiated and reviewed."""
import argparse,hashlib,json,os,sys,time
from pathlib import Path
HERE=Path(__file__).resolve().parent;sys.path.insert(0,str(HERE.parent))
from transport import call,payload,verify_freeze
from corpus import prompt
from grade import grade
def main(a):
 verify_freeze();lc=json.loads((HERE/'freeze.json').read_text(encoding='utf-8'));assert all(hashlib.sha256((HERE/n).read_bytes()).hexdigest()==h for n,h in lc['files'].items());cfg=json.loads((HERE/'config.json').read_text(encoding='utf-8'));folder=Path(a.output)/a.provider/(a.task+'-r'+str(a.round));assert not folder.exists();folder.mkdir(parents=True)
 text=prompt(a.task,cfg['filler_records'],a.round);messages=[{'role':'system','content':cfg['system']},{'role':'user','content':text}]
 body=payload(a.provider,os.environ['EVAL_MODEL'],messages,cfg['max_completion_tokens']);start=time.monotonic();r={'task':a.task,'provider':a.provider,'round':a.round,'prompt_sha256':hashlib.sha256(text.encode()).hexdigest(),'prompt_bytes':len(text.encode()),'started_at_epoch':time.time(),'model_requested':body['model']}
 try:
  import subprocess
  guard=json.loads(subprocess.check_output(json.loads(os.environ['EVAL_GUARD_COMMAND']),text=True));r['admission']=guard
  d,t=call(os.environ['EVAL_BASE_URL'],os.environ['EVAL_API_KEY'],body,cfg['http_timeout_s'],folder/'events.jsonl');r.update(response=d,latency=t,elapsed_s=time.monotonic()-start)
  u=d.get('usage',{});r['actual_prompt_tokens']=u.get('prompt_tokens');r['length_qualified']=isinstance(u.get('prompt_tokens'),int) and u['prompt_tokens']>100000
  c=d['choices'][0];r['content']=c['message'].get('content') or '';r['grade']=grade(a.task,r['content']);r['complete_hard']=r['length_qualified'] and r['grade']['pass'] and c['finish_reason']!='length'
  if u.get('completion_tokens',0)>cfg['max_completion_tokens']:r['error']='provider_output_limit_not_enforced';r['complete_hard']=False
 except Exception as e:r.update(error=str(e),elapsed_s=time.monotonic()-start,complete_hard=False)
 raw=json.dumps(r,ensure_ascii=False,indent=2);k=os.environ['EVAL_API_KEY'];assert not k or k not in raw;(folder/'result.json').write_text(raw+'\n',encoding='utf-8')
 if 'content' in r:(folder/'answer.txt').write_text(r['content'],encoding='utf-8')
 print(json.dumps({k:r.get(k) for k in ['task','provider','round','actual_prompt_tokens','length_qualified','complete_hard','elapsed_s','grade','error']},ensure_ascii=False),flush=True)
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--provider',choices=['local'],required=True);p.add_argument('--task',choices=['LC01','LC02'],required=True);p.add_argument('--round',type=int,required=True);p.add_argument('--output',required=True);main(p.parse_args())
