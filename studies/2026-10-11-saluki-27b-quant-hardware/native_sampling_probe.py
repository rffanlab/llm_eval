"""One registered native-sampling diagnostic; primary recordings are unchanged."""
import datetime,hashlib,json,os,pathlib,sys,time,urllib.request
S=pathlib.Path(__file__).resolve().parent;E=S.parents[1];sys.path.insert(0,str(E));from runner import grade
profile,case=sys.argv[1:3];registered=json.loads((S/'native-sampling-diagnostic.json').read_text());assert case in registered['cases']
frozen=json.loads((S/'freeze.json').read_text());assert profile in [h+'-'+m for h in frozen['hosts_order'] for m in frozen['profiles_order']]
for name,digest in frozen['hashes'].items():assert hashlib.sha256((S/name).read_bytes()).hexdigest()==digest,'original frozen source changed'
assert hashlib.sha256(pathlib.Path(__file__).read_bytes()).hexdigest()==registered['runner_sha256'],'diagnostic runner changed'
task=next(t for t in json.loads((S/'tasks.json').read_text(encoding='utf-8'))['tasks'] if t['id']==case);folder=S/'native-sampling'/profile/(case+'-r1');assert not folder.exists();folder.mkdir(parents=True)
payload={'model':os.environ['LOCAL_MODEL'],'messages':[{'role':'system','content':json.loads((S/'tasks.json').read_text(encoding='utf-8'))['system']},{'role':'user','content':task['prompt']}],'temperature':0.6,'top_p':0.95,'top_k':20,'min_p':0,'seed':42,'repeat_penalty':1,'presence_penalty':0,'chat_template_kwargs':{'enable_thinking':True},'max_tokens':8192,'stream':False,'cache_prompt':True}
record={'profile':profile,'kind':'native-sampling','case':case,'round':1,'thinking':True,'parameters':{k:v for k,v in payload.items() if k not in ['model','messages']},'started_at':datetime.datetime.now(datetime.timezone.utc).isoformat(),'timeout_s':240,'turns':[],'usage_complete':False};content='';started=time.monotonic()
(folder/'result.json').write_text(json.dumps(record,indent=2)+'\n',encoding='utf-8')
try:
 req=urllib.request.Request(os.environ['LOCAL_BASE_URL'].rstrip('/')+'/chat/completions',data=json.dumps(payload,ensure_ascii=False).encode(),headers={'Content-Type':'application/json','Authorization':'Bearer '+os.environ['LOCAL_API_KEY']})
 with urllib.request.urlopen(req,timeout=240) as r:data=json.load(r)
 message=data['choices'][0]['message'];content=message.get('content') or '';u=data.get('usage') or {};assert all(isinstance(u.get(k),int) for k in ['prompt_tokens','completion_tokens','total_tokens']);assert u['completion_tokens']<=8192
 record.update(usage_complete=True,usage=u);record['turns']=[{'index':1,'content':content,'reasoning_chars':len(message.get('reasoning_content') or ''),'usage':u,'timings':data.get('timings'),'finish_reason':data['choices'][0]['finish_reason'],'returned_model':data.get('model')}]
except Exception as exc:record['error']=type(exc).__name__+': '+str(exc)
record.update(content=content,elapsed_s=time.monotonic()-started);record['grade']={'pass':False,'error':record['error']} if record.get('error') else grade(task,content,folder)
(folder/'result.json').write_text(json.dumps(record,ensure_ascii=False,indent=2)+'\n',encoding='utf-8');(folder/'answer.txt').write_text(content,encoding='utf-8')
print(json.dumps({k:record.get(k) for k in ['profile','case','kind','elapsed_s','usage','usage_complete','grade','error']},ensure_ascii=False),flush=True)
