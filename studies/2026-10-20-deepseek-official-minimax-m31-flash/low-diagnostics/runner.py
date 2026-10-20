"""One preregistered exploratory low case; never overwrites primary results."""
import argparse,hashlib,json,os,sys,time
from pathlib import Path
HERE=Path(__file__).resolve().parent;S=HERE.parent;sys.path.insert(0,str(S))
from transport import call,payload,verify_freeze
def main(a):
 verify_freeze();files=json.loads((HERE/'freeze.json').read_text())['files'];assert all(hashlib.sha256((HERE/n).read_bytes()).hexdigest()==h for n,h in files.items())
 folder=S/'results/low-diagnostics'/a.provider/a.task;assert not folder.exists();folder.mkdir(parents=True)
 if a.task=='C03':
  suite=json.loads((S/'tasks.json').read_text());task=next(x for x in suite['tasks'] if x['id']=='C03');messages=[{'role':'system','content':suite['system']},{'role':'user','content':task['prompt']}]
 else:
  sys.path.insert(0,str(S/'long-context'));from corpus import prompt
  cfg=json.loads((S/'long-context/config.json').read_text());text=prompt('LC01',cfg['filler_records'],3);messages=[{'role':'system','content':cfg['system']},{'role':'user','content':text}]
 body=payload(a.provider,os.environ['EVAL_MODEL'],messages,8192,low=True);start=time.monotonic();r={'task':a.task,'provider':a.provider,'scope':'exploratory-low-after-max-budget-failures','reasoning_effort':'low','started_at_epoch':time.time(),'model_requested':body['model']}
 try:
  d,t=call(os.environ['EVAL_BASE_URL'],os.environ['EVAL_API_KEY'],body,240,folder/'events.jsonl');r.update(response=d,latency=t,elapsed_s=time.monotonic()-start);c=d['choices'][0];content=c['message'].get('content') or '';r['content']=content
  if a.task=='C03':
   sys.path.insert(0,str(S/'short-suite'));from runner import grade
   g=grade(task,content,folder);qualified=True
  else:
   from grade import grade
   g=grade('LC01',content);qualified=isinstance(d.get('usage',{}).get('prompt_tokens'),int) and d['usage']['prompt_tokens']>100000
  r['grade']=g;r['length_qualified']=qualified;r['complete_hard']=g['pass'] and qualified and c['finish_reason']!='length'
 except Exception as e:r.update(error=str(e),elapsed_s=time.monotonic()-start,complete_hard=False)
 (folder/'result.json').write_text(json.dumps(r,ensure_ascii=False,indent=2)+'\n',encoding='utf-8');(folder/'answer.txt').write_text(r.get('content',''),encoding='utf-8')
 print(json.dumps({k:r.get(k) for k in ['task','provider','scope','elapsed_s','grade','complete_hard','error']}|{'usage':r.get('response',{}).get('usage')},ensure_ascii=False),flush=True)
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--provider',choices=['deepseek','minimax'],required=True);p.add_argument('--task',choices=['C03','LC01'],required=True);main(p.parse_args())
