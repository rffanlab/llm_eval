"""Independent unscored warmup, never one of the seven capability tasks."""
import argparse,json,os,pathlib,subprocess,time
from transport import call,verify_freeze
p=argparse.ArgumentParser();p.add_argument('--block',required=True);p.add_argument('--output',required=True);a=p.parse_args();verify_freeze();profile=os.environ['EVAL_PROFILE'];root=pathlib.Path(a.output)/profile/('warmup_ready-'+a.block+'-r1');assert not root.exists();root.mkdir(parents=True)
admission=json.loads(subprocess.check_output(json.loads(os.environ['EVAL_GUARD_COMMAND']),text=True,timeout=30));(root/'admission.json').write_text(json.dumps(admission,indent=2)+'\n')
body={'model':os.environ['EVAL_MODEL'],'messages':[{'role':'user','content':'只回复两个汉字：就绪'}],'temperature':0,'seed':42,'max_tokens':128,'stream':True,'stream_options':{'include_usage':True},'reasoning_effort':'none','enable_thinking':False,'chat_template_kwargs':{'enable_thinking':False,'reasoning_effort':'none','preserve_thinking':False}}
r={'profile':profile,'kind':'warmup_ready-'+a.block,'round':1,'quality_scored':False,'payload':body,'started_at_epoch':time.time()}
try:r['response'],r['latency']=call(os.environ['EVAL_BASE_URL'],os.environ['EVAL_API_KEY'],body,240,root/'events.jsonl')
except Exception as e:r['error']=str(e)
(root/'result.json').write_text(json.dumps(r,ensure_ascii=False,indent=2)+'\n',encoding='utf-8');print(json.dumps({'warmup':a.block,'error':r.get('error'),'latency':r.get('latency'),'content':r.get('response',{}).get('choices',[{}])[0].get('message',{}).get('content')},ensure_ascii=False))
