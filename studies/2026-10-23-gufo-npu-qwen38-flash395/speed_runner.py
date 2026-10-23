"""A single registered speed request, explicitly launched; output quality is unscored."""
import argparse,json,os,pathlib,time,subprocess
from transport import call,verify_freeze
S=pathlib.Path(__file__).resolve().parent
def run(a):
 verify_freeze();prompts=json.loads((S/'speed-prompts.json').read_text(encoding='utf-8'));registered=next(x for x in prompts['cases'] if x['kind']==a.kind and x['round']==a.round);root=pathlib.Path(a.output)/a.profile/f'{a.kind}-r{a.round}';assert not root.exists();root.mkdir(parents=True)
 admission=json.loads(subprocess.check_output(json.loads(os.environ['EVAL_GUARD_COMMAND']),text=True,timeout=30));(root/'admission.json').write_text(json.dumps(admission,indent=2)+'\n')
 body={**registered['payload'],'model':os.environ['EVAL_MODEL'],'stream':True,'stream_options':{'include_usage':True},'reasoning_effort':'none','enable_thinking':False,'chat_template_kwargs':{'enable_thinking':False,'reasoning_effort':'none','preserve_thinking':False},'presence_penalty':0,'seed':42,'cache_prompt':False};r={'profile':a.profile,'kind':a.kind,'round':a.round,'quality_scored':False,'payload':body,'started_at_epoch':time.time()}
 try:r['response'],r['latency']=call(os.environ['EVAL_BASE_URL'],os.environ['EVAL_API_KEY'],body,1800,root/'events.jsonl')
 except Exception as e:r['error']=str(e)
 (root/'result.json').write_text(json.dumps(r,ensure_ascii=False,indent=2)+'\n',encoding='utf-8');print(json.dumps({'profile':a.profile,'kind':a.kind,'round':a.round,'latency':r.get('latency'),'timings':r.get('response',{}).get('timings'),'usage':r.get('response',{}).get('usage'),'error':r.get('error')},ensure_ascii=False),flush=True)
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--profile',required=True);p.add_argument('--kind',choices=['short512','prompt4k','prompt32k'],required=True);p.add_argument('--round',type=int,choices=[1,2,3],required=True);p.add_argument('--output',required=True);run(p.parse_args())
