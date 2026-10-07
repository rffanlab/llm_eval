"""One interactively initiated task per invocation; never loops over a suite."""
import argparse
import datetime as dt
import hashlib
import json
import os
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from agent_sim import Simulator,schemas

ROOT=Path(__file__).resolve().parent

def secret(name):
    value=os.environ.get(name)
    if value:return value
    if sys.platform=='win32':
        import winreg
        for hive,path in [(winreg.HKEY_CURRENT_USER,'Environment'),(winreg.HKEY_LOCAL_MACHINE,r'SYSTEM\CurrentControlSet\Control\Session Manager\Environment')]:
            try:
                with winreg.OpenKey(hive,path) as key:value=winreg.QueryValueEx(key,name)[0]
                if value:return value
            except OSError:pass
    raise RuntimeError('missing credential '+name)

def save(path,data):
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(data,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')

def grade(task,content,folder):
    if task['domain']=='code':
        file=folder/'submission.py';file.write_text(content,encoding='utf-8')
        try:
            p=subprocess.run([sys.executable,'-I',str(ROOT/'sandbox_grade.py'),task['id'],str(file)],capture_output=True,text=True,encoding='utf-8',timeout=5)
            return json.loads(p.stdout)
        except subprocess.TimeoutExpired:return {'score':0,'pass':False,'error':'execution_timeout_5s'}
        except Exception:return {'score':0,'pass':False,'error':'grader_process_error'}
    if task.get('expected') is not None:
        try:data=json.loads(content)
        except Exception:data={}
        if not isinstance(data,dict):data={}
        expected=task['expected'];checks={k:data.get(k)==v for k,v in expected.items()};checks['exact_keys']=set(data)==set(expected)
    else:
        c=task['checks'];length=len(''.join(content.split()))
        checks={'length':c['min_chars']<=length<=c['max_chars'],**{f'has_{s}':s in content for s in c['required']}}
        if 'paragraphs' in c:checks['paragraphs']=len([x for x in content.split('\n\n') if x.strip()])==c['paragraphs']
        return {'score':round(100*sum(checks.values())/len(checks),2),'pass':all(checks.values()),'checks':checks,'nonspace_chars':length,'editor_review_pending':True}
    return {'score':round(100*sum(checks.values())/len(checks),2),'pass':all(checks.values()),'checks':checks}

def main():
    if hasattr(sys.stdout,'reconfigure'):sys.stdout.reconfigure(encoding='utf-8')
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--provider',choices=['local','official'],required=True)
    p.add_argument('--task',required=True)
    p.add_argument('--round',type=int,default=1)
    p.add_argument('--diagnostic',choices=['writing-budget-8192','total-budget-8192'])
    p.add_argument('--output',type=Path,default=ROOT/'studies/2026-10-07-local-vs-cloud/results')
    a=p.parse_args()
    raw=(ROOT/'suite/tasks.json').read_bytes();suite=json.loads(raw)
    task=next(x for x in suite['tasks'] if x['id']==a.task)
    if a.diagnostic:
        allowed=['W02'] if a.diagnostic=='writing-budget-8192' else ['W02','W03','C03']
        if a.task not in allowed or a.round!=1:raise SystemExit('unregistered diagnostic case')
        task=dict(task,max_tokens=8192)
        a.output=ROOT/'studies/2026-10-07-local-vs-cloud/diagnostics'/a.diagnostic
    if a.round not in (1,2,3) or (a.round>1 and a.task not in suite['repeat_tasks']):raise SystemExit('unregistered repeat')
    folder=a.output/f'{a.task}-{a.provider}-r{a.round}'
    if folder.exists():raise SystemExit('preserve existing attempt; never overwrite or auto retry')
    if a.provider=='local':
        base=os.environ['LOCAL_BASE_URL'];key=secret('LOCAL_API_KEY');model=os.environ.get('LOCAL_MODEL','Qwen/Qwen3.8-Flash-Next')
    else:
        base='https://token-plan.cn-beijing.maas.aliyuncs.com/compatible-mode/v1';key=secret('QWEN_API_KEY');model='qwen3.8-flash'
    existing=[json.loads(x.read_text(encoding='utf-8')) for x in a.output.glob('*/result.json')]
    if sum(x.get('usage',{}).get('total_tokens',0) for x in existing)>=400000:raise SystemExit('study token review threshold reached')
    record={'task':a.task,'provider':a.provider,'round':a.round,'model_requested':model,'fixture_sha256':hashlib.sha256(raw).hexdigest(),'started_at':dt.datetime.now(dt.timezone(dt.timedelta(hours=8))).isoformat(),'parameters':{'temperature':0,'enable_thinking':True,'max_tokens':task['max_tokens'],'stream':False},'turns':[]}
    if a.diagnostic=='total-budget-8192' and a.provider=='official':
        record['parameters']['max_completion_tokens']=record['parameters'].pop('max_tokens')
    if a.diagnostic:record['diagnostic']=a.diagnostic
    messages=[{'role':'system','content':suite['system']},{'role':'user','content':task['prompt']}]
    sim=Simulator(a.task) if task['domain']=='agent' else None
    remaining=task['max_tokens'];usage={'prompt_tokens':0,'completion_tokens':0,'total_tokens':0};content='';started=time.monotonic()
    folder.mkdir(parents=True)
    try:
        for turn in range(6 if sim else 1):
            if remaining<=0:record['error']='task_output_budget_exhausted';break
            payload={'model':model,'messages':messages,'temperature':0,'enable_thinking':True,'max_tokens':remaining,'stream':False}
            if a.diagnostic=='total-budget-8192' and a.provider=='official':payload['max_completion_tokens']=payload.pop('max_tokens')
            if sim:payload.update(tools=schemas(a.task),tool_choice='auto',parallel_tool_calls=False)
            req=urllib.request.Request(base.rstrip('/')+'/chat/completions',data=json.dumps(payload,ensure_ascii=False).encode(),headers={'Content-Type':'application/json','Authorization':'Bearer '+key})
            at=time.monotonic()
            try:
                with urllib.request.urlopen(req,timeout=240) as resp:data=json.load(resp)
            except urllib.error.HTTPError as exc:raise RuntimeError(f'HTTP {exc.code}') from None
            except urllib.error.URLError as exc:raise RuntimeError('network '+type(exc.reason).__name__) from None
            elapsed=time.monotonic()-at
            choice=data['choices'][0];message=choice['message'];content=message.get('content') or '';u=data.get('usage') or {}
            if not all(isinstance(u.get(k),int) for k in usage):raise RuntimeError('usage_missing')
            for k in usage:usage[k]+=u[k]
            remaining-=u['completion_tokens']
            calls=message.get('tool_calls') or []
            record['turns'].append({'index':turn+1,'elapsed_s':round(elapsed,4),'returned_model':data.get('model'),'content':content,'reasoning_chars':len(message.get('reasoning_content') or ''),'tool_calls':calls,'usage':u,'finish_reason':choice.get('finish_reason'),'timings':data.get('timings')})
            record.update(usage=usage,content=content,elapsed_s=round(time.monotonic()-started,4))
            save(folder/'result.json',record)
            if not calls:break
            if not sim:raise RuntimeError('unexpected_tool_call')
            # Preserve reasoning in the next in-memory message if the API provided it;
            # publish final answer and reasoning length only.
            messages.append(message)
            for call in calls:
                try:args=json.loads(call['function']['arguments'])
                except Exception:args={}
                result=sim.invoke(call['function']['name'],args)
                messages.append({'role':'tool','tool_call_id':call['id'],'content':json.dumps(result,ensure_ascii=False)})
        else:
            if sim:record['error']='agent_turn_limit'
    except Exception as exc:record['error']=type(exc).__name__+': '+str(exc)
    record.update(usage=usage,content=content,elapsed_s=round(time.monotonic()-started,4),human_corrections=0)
    record['usage_complete']=not bool(record.get('error'))
    if sim:record['tool_trace']=sim.trace
    record['grade']={'score':0,'pass':False,'error':record['error']} if record.get('error') else (sim.grade(content) if sim else grade(task,content,folder))
    record['end_to_end_output_tps']=round(usage['completion_tokens']/record['elapsed_s'],3) if record['elapsed_s'] else None
    save(folder/'result.json',record)
    (folder/'answer.txt').write_text(content,encoding='utf-8')
    print(json.dumps({k:record[k] for k in ['task','provider','round','elapsed_s','usage','grade']},ensure_ascii=False),flush=True)

if __name__=='__main__':main()
