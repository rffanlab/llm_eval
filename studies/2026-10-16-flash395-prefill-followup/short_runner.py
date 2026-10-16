"""One explicitly initiated case; frozen GSQ/Unsloth quantization comparison."""
import argparse,hashlib,json,os,pathlib,sys,time,subprocess,threading
from transport import call,payload,history,verify_freeze
S=pathlib.Path(__file__).resolve().parent;sys.path.insert(0,str(S/'short-suite'))
from runner import grade,save
from agent_sim import Simulator,schemas
from resource_probe import sampler

def run(a):
    verify_freeze()
    suite=json.loads((S/'tasks.json').read_text(encoding='utf-8'));task=next(x for x in suite['tasks'] if x['id']==a.task)
    assert a.round in [1,2];assert a.variant=='main' or a.task=='D01'
    folder=pathlib.Path(a.output)/a.variant/a.provider/(a.task+'-r'+str(a.round));assert not folder.exists(),'preserve existing attempt';folder.mkdir(parents=True)
    model=os.environ['EVAL_MODEL'];base=os.environ['EVAL_BASE_URL'];key=os.environ['EVAL_API_KEY'];guard=json.loads(os.environ['EVAL_GUARD_COMMAND']) if a.provider=='local' else None
    messages=[{'role':'system','content':suite['system']},{'role':'user','content':task['prompt']}];sim=Simulator(a.task) if task['domain']=='agent' else None
    r={'task':a.task,'provider':a.provider,'profile':os.environ['EVAL_PROFILE'],'round':a.round,'variant':a.variant,'model_requested':model,'fixture_sha256':hashlib.sha256((S/'tasks.json').read_bytes()).hexdigest(),'usage':{k:0 for k in ['prompt_tokens','completion_tokens','total_tokens']},'usage_complete':True,'turns':[],'started_at_epoch':time.time(),'human_corrections':0}
    stop=threading.Event();thread=threading.Thread(target=sampler,args=(stop,folder/'resources.jsonl'),daemon=True);thread.start()
    start=time.monotonic();remaining=task['max_tokens'];content=''
    try:
        for turn in range(6 if sim else 1):
            if remaining<=0:raise RuntimeError('total_output_budget_exhausted')
            if time.monotonic()-start>=480:raise RuntimeError('task_wall_budget')
            if guard:
                admission=json.loads(subprocess.check_output(guard,text=True,timeout=30));save(folder/f'admission-{turn+1}.json',admission)
            body=payload(a.provider,model,messages,remaining,schemas(a.task) if sim else None,a.variant=='depth')
            data,timing=call(base,key,body,min(240,480-(time.monotonic()-start)),folder/f'events-{turn+1}.jsonl')
            save(folder/f'call-{turn+1}.json',{'payload':body,'response':data,'latency':timing})
            choice=data['choices'][0];message=choice['message'];content=message.get('content') or '';u=data.get('usage') or {}
            tr={'index':turn+1,'content':content,'returned_model':data.get('model'),'reasoning_chars':len(message.get('reasoning_content') or ''),'tool_calls':message.get('tool_calls') or [],'usage':u,'finish_reason':choice.get('finish_reason'),'timings':data.get('timings'),**timing};r['turns'].append(tr)
            for k in r['usage']:
                if isinstance(u.get(k),int):r['usage'][k]+=u[k]
                else:r['usage_complete']=False
            if not isinstance(u.get('completion_tokens'),int):raise RuntimeError('output_usage_missing')
            if u['completion_tokens']>remaining:raise RuntimeError('provider_output_limit_not_enforced')
            remaining-=u['completion_tokens'];calls=message.get('tool_calls') or [];messages.append(history(a.provider,message));save(folder/'result.json',r)
            if choice.get('finish_reason')=='length':raise RuntimeError('output_truncated')
            if not calls:break
            if not sim:raise RuntimeError('unexpected_tool_call')
            if len(calls)!=1:raise RuntimeError('one_tool_per_reply_required')
            for c in calls:
                result=sim.invoke(c['function']['name'],json.loads(c['function']['arguments']));messages.append({'role':'tool','tool_call_id':c['id'],'content':json.dumps(result,ensure_ascii=False)})
        else:
            if sim:raise RuntimeError('agent_reply_budget_exhausted')
    except Exception as e:r['error']=str(e).replace(key,'[REDACTED]');r['usage_complete']=False
    stop.set();thread.join(timeout=3)
    r.update(content=content,elapsed_s=time.monotonic()-start,reasoning_chars=sum(t['reasoning_chars'] for t in r['turns']))
    if sim:r['tool_trace']=sim.trace
    grading_start=time.monotonic()
    r['grade']={'score':0,'pass':False,'error':r['error']} if r.get('error') else sim.grade(content) if sim else grade(task,content,folder)
    r['hidden_grading_s_excluded']=time.monotonic()-grading_start
    save(folder/'result.json',r);(folder/'answer.txt').write_text(content,encoding='utf-8')
    print(json.dumps({k:r.get(k) for k in ['task','provider','round','variant','elapsed_s','usage','grade','error']},ensure_ascii=False),flush=True)
    return r
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--provider',choices=['local'],required=True);p.add_argument('--task',required=True);p.add_argument('--round',type=int,required=True);p.add_argument('--variant',choices=['main','depth'],default='main');p.add_argument('--output',required=True);run(p.parse_args())
