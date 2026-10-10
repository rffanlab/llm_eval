"""Public replay adapter: use only process environment, no private host configuration."""
import argparse,json,runpy,sys,urllib.request
from pathlib import Path
import os
S=Path(__file__).resolve().parent;ROOT=S.parents[1];sys.path.insert(0,str(ROOT))
p=argparse.ArgumentParser();p.add_argument('--profile',required=True);p.add_argument('--kind',choices=['main','thinking','capacity','probe'],required=True);p.add_argument('--task');p.add_argument('--round',type=int,default=1);p.add_argument('--thinking',choices=['on','off'],default='on');p.add_argument('--context',type=int);p.add_argument('--capacity-kind',choices=['retrieval','probe']);p.add_argument('--single-model-confirmed',action='store_true');a=p.parse_args()
assert a.single_model_confirmed,'Stop other inference services and inspect processes/available RAM before every request. This flag is an operator attestation, not an automatic resource guard.'
assert all(os.environ.get(x) for x in ['LOCAL_BASE_URL','LOCAL_API_KEY','LOCAL_MODEL'])
if a.kind=='main':
 sys.argv=['runner.py','--provider','local','--profile',a.profile,'--study',str(S),'--suite',str(S/'tasks.json'),'--output',str(S/'private-replay'/a.profile),'--task',a.task,'--round',str(a.round),'--thinking',a.thinking,'--reasoning-effort','medium','--preserve-thinking','off','--presence-penalty','0'];runpy.run_path(str(ROOT/'runner.py'),run_name='__main__')
elif a.kind=='thinking':
 from overthinking_runner import run
 run(S,a.profile,a.task,a.thinking,a.round,'overthinking-native-tasks.json','private-thinking-replay','medium',False,0)
elif a.kind=='capacity':
 sys.argv=['capacity_runner.py','--study',str(S),'--profile',a.profile,'--context',str(a.context),'--kind',a.capacity_kind];runpy.run_path(str(S/'capacity_runner.py'),run_name='__main__')
else:
 payload=json.loads((S/'speed-probe-prompt.json').read_text(encoding='utf-8'));payload.update(model=os.environ['LOCAL_MODEL'],reasoning_effort='none',presence_penalty=0,chat_template_kwargs={'enable_thinking':False,'reasoning_effort':'none','preserve_thinking':False})
 f=S/'private-speed-replay'/a.profile/f'r{a.round}.json';assert not f.exists();req=urllib.request.Request(os.environ['LOCAL_BASE_URL'].rstrip('/')+'/chat/completions',data=json.dumps(payload).encode(),headers={'Authorization':'Bearer '+os.environ['LOCAL_API_KEY'],'Content-Type':'application/json'})
 with urllib.request.urlopen(req,timeout=120) as r:response=json.load(r)
 f.parent.mkdir(parents=True,exist_ok=True);f.write_text(json.dumps({'payload':payload,'response':response},ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
