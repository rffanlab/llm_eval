"""One explicitly initiated long-horizon episode; local endpoints via environment."""
import argparse,hashlib,json,os,subprocess,sys,threading,time,urllib.request
from pathlib import Path
from fixture import files,expected
from grade import isolated,report_grade
HERE=Path(__file__).resolve().parent
def sha(b):return hashlib.sha256(b).hexdigest()
def save(path,d):
    path.parent.mkdir(parents=True,exist_ok=True);tmp=path.with_suffix(path.suffix+'.tmp');tmp.write_text(json.dumps(d,ensure_ascii=False,indent=2)+'\n',encoding='utf-8');tmp.replace(path)
def freeze():return {p.name:sha(p.read_bytes()) for p in HERE.glob('*') if p.is_file() and p.suffix in ['.py','.json'] and p.name!='freeze.json'}
TOOLS=[{'type':'function','function':{'name':name,'description':description,'parameters':schema}} for name,description,schema in [
 ('list_files','列出当前可读取文件，包括工作区和当前发布。',{'type':'object','properties':{},'additionalProperties':False}),
 ('read_file','读取指定文件。',{'type':'object','properties':{'path':{'type':'string'}},'required':['path'],'additionalProperties':False}),
 ('write_file','写入整个workflow.py或delivery.md，其他路径不允许修改。',{'type':'object','properties':{'path':{'type':'string'},'content':{'type':'string'}},'required':['path','content'],'additionalProperties':False}),
 ('run_tests','运行当前阶段公开visible功能测试，显示失败细节。隐藏验收不会反馈。',{'type':'object','properties':{},'additionalProperties':False}),
 ('reconcile','执行指定数据集，返回对账结果。',{'type':'object','properties':{'dataset':{'type':'string','enum':['base','v2','final']}},'required':['dataset'],'additionalProperties':False}),
 ('publish','通过事务发布指定数据集。首次发布会出现一次临时磁盘故障，可依据返回重试。',{'type':'object','properties':{'dataset':{'type':'string','enum':['v2','final']}},'required':['dataset'],'additionalProperties':False})]]

class Workspace:
    def __init__(self,root):
        self.root=root;self.data={};self.events=[];self.injected=False;self.published={};self.stage=0
        self.current=root/'release';self.current.mkdir(parents=True)
        (self.current/'previous.txt').write_text('previous release must survive a failed transaction',encoding='utf-8')
    def advance(self,stage):
        self.stage=stage
        for k,v in files(stage).items():
            if k not in self.data:self.data[k]=v;self.persist(k,v)
    def persist(self,k,v):
        p=self.root/k;p.parent.mkdir(parents=True,exist_ok=True);p.write_text(v,encoding='utf-8')
    def read(self,k):
        if k in self.data:return self.data[k]
        if k.startswith('release/'):
            p=self.current/k.split('/',1)[1]
            if p.name in ['orders.csv','customers.csv','summary.json','manifest.json','previous.txt'] and p.exists():return p.read_text(encoding='utf-8')
        raise ValueError('file unavailable')
    def act(self,name,args):
        if name=='list_files':return {'files':sorted(self.data)+['release/'+p.name for p in self.current.iterdir() if p.is_file()]}
        if name=='read_file':return {'path':args['path'],'content':self.read(args['path'])}
        if name=='write_file':
            k=args['path'];assert k in ['workflow.py','delivery.md'],'read-only input/specification'
            assert isinstance(args['content'],str) and len(args['content'])<=50000,'file size limit'
            self.data[k]=args['content'];self.persist(k,args['content']);return {'written':k,'bytes':len(args['content'].encode())}
        if name=='run_tests':return isolated(self.data['workflow.py'],stage=self.stage,visible=True)
        if name in ['reconcile','publish']:
            ds=args['dataset'];assert ds in ['base','v2','final'] and ('data/'+ds+'/orders.csv') in self.data,'dataset not released yet'
            out=isolated(self.data['workflow.py'],action='reconcile' if name=='reconcile' else 'bundle',dataset=ds)
            if name=='reconcile' or 'error' in out:return out
            bundle=out['bundle'];assert isinstance(bundle,dict) and set(bundle)=={'orders.csv','customers.csv','summary.json'},'bundle names do not match contract'
            assert all(isinstance(x,str) and len(x)<100000 for x in bundle.values()),'invalid bundle values'
            before={p.name:sha(p.read_bytes()) for p in self.current.iterdir() if p.is_file()}
            staging=self.root/'staging';staging.mkdir(exist_ok=True)
            for i,(k,v) in enumerate(sorted(bundle.items())):
                (staging/k).write_text(v,encoding='utf-8')
                if not self.injected:
                    self.injected=True
                    after={p.name:sha(p.read_bytes()) for p in self.current.iterdir() if p.is_file()}
                    return {'error':'ENOSPC_INJECTED','temporary_fault_cleared':True,'previous_release_unchanged':before==after,'staged_files':[k],'published':False}
            manifest={'dataset':ds,'sha256':{k:sha((staging/k).read_bytes()) for k in sorted(bundle)}}
            save(staging/'manifest.json',manifest)
            backup=self.root/'previous-release'
            if backup.exists():
                # Only harness-owned, fixed sandbox folder. No model-controlled path.
                import shutil
                shutil.rmtree(backup)
            self.current.replace(backup);staging.replace(self.current)
            self.published={'dataset':ds,'result':out['result'],'bundle_grade':out['grade'],'manifest':manifest}
            return {'published':True,'dataset':ds,'files':sorted(bundle),'manifest':manifest,'totals':out['result']['totals']}
        raise ValueError('unknown tool')
    def grade(self):
        source=self.data['workflow.py'];functional=isolated(source,stage=self.stage)
        checks=list(functional.get('checks',[]))
        if self.stage>=3:
            ds='final' if self.stage==4 else 'v2'
            out=isolated(source,action='bundle',dataset=ds)
            checks+=out.get('grade',{'checks':[{'name':'export_bundle_execution','pass':False}]}).get('checks',[])
            checks+=[{'name':'current_publication_'+ds,'pass':self.published.get('dataset')==ds and self.published.get('result')==expected(ds)}, {'name':'fault_observed_and_recovered','pass':self.injected and any(e['result'].get('published') for e in self.events)}, {'name':'failed_transaction_kept_previous','pass':any(e['result'].get('previous_release_unchanged') is True for e in self.events)}]
            if self.published:
                manifest=self.published['manifest'];checks.append({'name':'manifest_matches_bytes','pass':all((self.current/k).exists() and sha((self.current/k).read_bytes())==v for k,v in manifest['sha256'].items())})
        if self.stage==4:checks+=report_grade(self.data.get('delivery.md',''),self.published,self.events)['checks']
        return {'checks':checks,'pass':bool(checks) and all(c['pass'] for c in checks),'passed':sum(bool(c['pass']) for c in checks),'total':len(checks)}

def sampler(stop,path):
    if sys.platform=='win32':return
    with path.open('a',encoding='utf-8') as f:
        while not stop.is_set():
            row={'epoch':time.time()};row['MemAvailable_bytes']=next(int(l.split()[1])*1024 for l in Path('/proc/meminfo').read_text().splitlines() if l.startswith('MemAvailable:'))
            row['gpu']=[]
            for p in Path('/sys/class/drm').glob('card*/device'):
                if '-' in p.parent.name or not (p/'mem_info_gtt_used').exists():continue
                row['gpu'].append({'pci':p.resolve().name,'GTT':int((p/'mem_info_gtt_used').read_text()),'VRAM':int((p/'mem_info_vram_used').read_text())})
            f.write(json.dumps(row)+'\n');f.flush();stop.wait(1)

def run(a):
    declared=json.loads((HERE/'freeze.json').read_text(encoding='utf-8'))['files'];assert declared==freeze(),'task suite changed after freezing'
    task=json.loads((HERE/'task.json').read_text(encoding='utf-8'));budget=task['budget']
    root=Path(a.output)/a.profile/('r'+str(a.round));assert not root.exists(),'preserve existing episode'
    root.mkdir(parents=True);w=Workspace(root/'workspace');base=os.environ['LOCAL_BASE_URL'];key=os.environ['LOCAL_API_KEY'];model=os.environ['LOCAL_MODEL']
    guard=os.environ.get('LOCAL_GUARD_COMMAND');assert guard,'every API call requires a registered automatic single-model resource guard'
    messages=[{'role':'system','content':task['system']}];record={'task':'LH01','profile':a.profile,'round':a.round,'model_requested':model,'freeze':declared,'parameters':budget,'stages':[],'usage':{'prompt_tokens':0,'completion_tokens':0,'total_tokens':0},'usage_complete':True,'started_at_epoch':time.time(),'human_corrections':0,'simulated_incidents':1}
    stop=threading.Event();thread=threading.Thread(target=sampler,args=(stop,root/'resources.jsonl'),daemon=True);thread.start();episode_start=time.monotonic();hidden_s=0
    try:
        for stage_no,stage in enumerate(task['stages'],1):
            w.advance(stage_no);messages.append({'role':'user','content':stage['prompt']});start=time.monotonic();s={'id':stage['id'],'name':stage['name'],'turns':[],'tool_events':[],'finished_with_answer':False}
            record['stages'].append(s)
            for turn in range(stage['max_calls']):
                if time.monotonic()-episode_start-hidden_s>=budget['max_wall_seconds_episode']:s['error']='episode_wall_budget';break
                remaining=budget['max_completion_tokens_episode']-record['usage']['completion_tokens']
                if remaining<=0:s['error']='episode_completion_budget';break
                gd=subprocess.run(json.loads(guard),capture_output=True,text=True,timeout=30)
                if gd.returncode:raise RuntimeError('resource admission rejected: '+gd.stderr[-500:])
                admission=json.loads(gd.stdout);save(root/'admission'/f'{stage_no}-{turn+1}.json',admission)
                payload={'model':model,'messages':messages,'tools':TOOLS,'tool_choice':'auto','parallel_tool_calls':False,'temperature':0,'stream':False,'max_tokens':min(budget['max_tokens_per_call'],remaining),'reasoning_effort':'medium','enable_thinking':True,'chat_template_kwargs':{'enable_thinking':True,'reasoning_effort':'medium','preserve_thinking':False},'presence_penalty':0}
                req=urllib.request.Request(base.rstrip('/')+'/chat/completions',data=json.dumps(payload,ensure_ascii=False).encode(),headers={'Authorization':'Bearer '+key,'Content-Type':'application/json'})
                callstart=time.monotonic()
                try:
                    with urllib.request.urlopen(req,timeout=min(budget['http_timeout_seconds'],max(1,budget['max_wall_seconds_episode']-(time.monotonic()-episode_start-hidden_s)))) as r:data=json.load(r)
                except Exception as e:
                    s['error']=str(e);record['usage_complete']=False;s['turns'].append({'index':turn+1,'elapsed_s':time.monotonic()-callstart,'error':str(e),'usage':None});break
                elapsed=time.monotonic()-callstart;message=data['choices'][0]['message'];usage=data.get('usage',{});choice=data['choices'][0]
                tr={'index':turn+1,'elapsed_s':elapsed,'returned_model':data.get('model'),'content':message.get('content') or '', 'tool_calls':message.get('tool_calls',[]),'reasoning_chars':len(message.get('reasoning_content') or ''),'usage':usage,'timings':data.get('timings'),'finish_reason':choice.get('finish_reason')};s['turns'].append(tr)
                for k in record['usage']:
                    if isinstance(usage.get(k),int):record['usage'][k]+=usage[k]
                    else:record['usage_complete']=False
                save(root/'calls'/f'{stage_no}-{turn+1}.json',{'payload':payload,'response':{**data,'choices':[{**choice,'message':{k:v for k,v in message.items() if k!='reasoning_content'}}]},'reasoning_chars':tr['reasoning_chars'],'elapsed_s':elapsed})
                calls=message.get('tool_calls') or [];messages.append({'role':'assistant','content':message.get('content') or '',**({'tool_calls':calls} if calls else {})})
                if not calls:
                    s['finished_with_answer']=True;s['final_answer']=tr['content'];break
                for c in calls:
                    t0=time.monotonic();fn=c['function']
                    try:
                        if len(calls)!=1:raise ValueError('one tool per turn required')
                        result=w.act(fn['name'],json.loads(fn['arguments']))
                    except Exception as e:result={'error':str(e)}
                    event={'stage':stage['id'],'turn':turn+1,'tool':fn['name'],'arguments':fn['arguments'],'result':result,'elapsed_s':time.monotonic()-t0};w.events.append(event);s['tool_events'].append(event)
                    messages.append({'role':'tool','tool_call_id':c['id'],'content':json.dumps(result,ensure_ascii=False)})
                save(root/'record.json',record)
            else:s['error']='stage_call_budget'
            s['elapsed_s']=time.monotonic()-start
            t0=time.monotonic();s['grade']=w.grade();hidden_s+=time.monotonic()-t0
            s['workflow_sha256']=sha(w.data['workflow.py'].encode());s['publication']=w.published.copy();save(root/'snapshots'/('S'+str(stage_no)+'.json'),{'files':w.data,'grade':s['grade'],'publication':s['publication']})
            # Do not send independent grade or oracle answers back to the model.
            save(root/'record.json',record)
            print(json.dumps({'profile':a.profile,'round':a.round,'stage':stage['id'],'calls':len(s['turns']),'elapsed_s':round(s['elapsed_s'],2),'hard_pass':s['grade']['pass'],'checks':str(s['grade']['passed'])+'/'+str(s['grade']['total'])}),flush=True)
    except Exception as e:record['error']=str(e)
    finally:
        stop.set();thread.join(timeout=2);record['elapsed_s']=time.monotonic()-episode_start-hidden_s;record['hidden_grading_s_excluded']=hidden_s
        record['complete_delivery']=len(record['stages'])==4 and all(s.get('grade',{}).get('pass') and s.get('finished_with_answer') and not s.get('error') for s in record['stages'])
        record['tool_calls']=len(w.events);record['reasoning_chars']=sum(t.get('reasoning_chars',0) for s in record['stages'] for t in s['turns']);save(root/'record.json',record);save(root/'tool-ledger.json',w.events)
        print(json.dumps({'profile':a.profile,'round':a.round,'complete_delivery':record['complete_delivery'],'elapsed_s':round(record['elapsed_s'],2),'usage':record['usage'],'error':record.get('error')}),flush=True)
    return record
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--profile',required=True);p.add_argument('--round',type=int,required=True);p.add_argument('--output',required=True);run(p.parse_args())
