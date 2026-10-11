"""One frozen recording. API credentials/base URL are supplied only in environment."""
import argparse,datetime,hashlib,json,os,pathlib,sys,time,urllib.request,urllib.error
S=pathlib.Path(__file__).resolve().parent;E=S.parents[1];sys.path.insert(0,str(E))
from runner import grade
from agent_sim import Simulator,schemas
p=argparse.ArgumentParser();p.add_argument('profile');p.add_argument('kind',choices=['main','thinking','probe','timing','preflight']);p.add_argument('case');p.add_argument('--round',type=int,default=1);p.add_argument('--thinking',choices=['on','off'],default='on');p.add_argument('--repeat',choices=['new-prefix','exact-repeat']);a=p.parse_args()
frozen=json.loads((S/'freeze.json').read_text());assert a.profile in [h+'-'+m for h in frozen['hosts_order'] for m in frozen['profiles_order']]
for name,digest in frozen['hashes'].items():assert hashlib.sha256((S/name).read_bytes()).hexdigest()==digest,'frozen source changed: '+name
stamp=datetime.datetime.now(datetime.timezone.utc).isoformat();group='preflight' if a.kind=='preflight' else 'thinking-complex' if a.kind=='main' and a.thinking=='off' else a.kind
name=a.case+'-'+a.thinking+'-r'+str(a.round) if a.kind=='thinking' else a.case+'-'+a.repeat if a.kind=='timing' else a.case+'-r'+str(a.round)
folder=S/group/a.profile/name;target=folder/'result.json';assert not folder.exists(),'Preserve first attempt'
folder.mkdir(parents=True)
suite=json.loads((S/'tasks.json').read_text(encoding='utf-8'));task=None;sim=None
thinking=a.thinking=='on'
if a.kind in ['main','preflight']:
 if a.kind=='preflight' and a.case=='O01':
  task={'id':'O01','domain':'reasoning','prompt':'计算37×43，只输出结果整数，不加标点。','max_tokens':128};messages=[{'role':'system','content':'严格遵守格式。'},{'role':'user','content':task['prompt']}];thinking=False
 else:
  task=next(x for x in suite['tasks'] if x['id']==a.case);messages=[{'role':'system','content':suite['system']},{'role':'user','content':task['prompt']}]
  if task['domain']=='agent':sim=Simulator(a.case)
 budget=task['max_tokens'];deadline=frozen['short_timeout_s'] if a.case in frozen['short_tasks'] else frozen['complex_timeout_s']
elif a.kind=='thinking':
 suite=json.loads((S/'overthinking-native-tasks.json').read_text(encoding='utf-8'));task=next(x for x in suite['cases'] if x['id']==a.case)
 messages=[{'role':'system','content':suite['system']},{'role':'user','content':task['prompt']}];budget=suite['max_tokens'];deadline=90
elif a.kind=='probe':
 payload=json.loads((S/'speed-probe-prompt.json').read_text(encoding='utf-8'));messages=payload['messages'];budget=512;deadline=240;thinking=False
else:
 fixture=next(x for x in json.loads((S/'timing-fixtures.json').read_text(encoding='utf-8')) if x['id']==a.case);messages=fixture['messages'];budget=512;deadline=600;thinking=False
base=os.environ['LOCAL_BASE_URL'];model=os.environ['LOCAL_MODEL'];key=os.environ['LOCAL_API_KEY']
record={'profile':a.profile,'kind':a.kind,'case':a.case,'round':a.round,'thinking':thinking,'started_at':stamp,'output_budget':budget,'timeout_s':deadline,'turns':[],'usage_complete':False,'human_corrections':0}
record['parameters']={'temperature':0,'seed':42,'top_p':1,'top_k':0,'min_p':0,'repeat_penalty':1,'presence_penalty':0,'chat_template_kwargs':{'enable_thinking':thinking},'cache_prompt':a.kind!='probe'}
aggregate={'prompt_tokens':0,'completion_tokens':0,'total_tokens':0};remaining=budget;content='';started=time.monotonic()
def save():target.write_text(json.dumps(record,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
save()
try:
 for turn in range(6 if sim else 1):
  if remaining<=0:raise RuntimeError('task_output_budget_exhausted')
  left=deadline-(time.monotonic()-started)
  if left<=0:raise TimeoutError('task deadline')
  streaming=a.kind=='timing'
  payload={**record['parameters'],'model':model,'messages':messages,'max_tokens':remaining,'stream':streaming}
  if a.kind=='probe':payload['ignore_eos']=True
  if streaming:payload['stream_options']={'include_usage':True}
  if sim:payload.update(tools=schemas(a.case),tool_choice='auto',parallel_tool_calls=False)
  req=urllib.request.Request(base.rstrip('/')+'/chat/completions',data=json.dumps(payload,ensure_ascii=False).encode(),headers={'Content-Type':'application/json','Authorization':'Bearer '+key})
  at=time.monotonic()
  with urllib.request.urlopen(req,timeout=max(.1,left)) as response:
   if not streaming:data=json.load(response)
   else:
    chunks=[];answer=[];thought=[];usage=None;timings=None;finished=None
    record['chunks']=chunks
    record.update(first_sse_chunk_s=None,first_content_delta_s=None,first_reasoning_delta_s=None,first_nonempty_delta_s=None)
    for raw in response:
     if time.monotonic()-started>deadline:raise TimeoutError('stream task deadline')
     line=raw.decode('utf-8').strip()
     if not line.startswith('data:'):continue
     text=line[5:].strip()
     if text=='[DONE]':record['done_event']=True;break
     chunk=json.loads(text);when=time.monotonic()-at;chunks.append({'arrival_s':when,'data':chunk})
     if record['first_sse_chunk_s'] is None:record['first_sse_chunk_s']=when
     if chunk.get('usage'):usage=chunk['usage']
     if chunk.get('timings'):timings=chunk['timings']
     for choice in chunk.get('choices',[]):
      delta=choice.get('delta') or {};c=delta.get('content') or '';r=delta.get('reasoning_content') or ''
      if c:
       answer.append(c);record['partial_stream_content']=''.join(answer)
       if record['first_content_delta_s'] is None:record['first_content_delta_s']=when
      if r:
       thought.append(r);record['partial_stream_reasoning_chars']=len(''.join(thought))
       if record['first_reasoning_delta_s'] is None:record['first_reasoning_delta_s']=when
      if (c or r) and record['first_nonempty_delta_s'] is None:record['first_nonempty_delta_s']=when
      if choice.get('finish_reason') is not None:finished=choice['finish_reason']
    record['chunks']=chunks
    data={'choices':[{'message':{'role':'assistant','content':''.join(answer),'reasoning_content':''.join(thought)},'finish_reason':finished}],'usage':usage,'timings':timings,'model':model}
  choice=data['choices'][0];message=choice['message'];content=message.get('content') or '';u=data.get('usage') or {}
  if not all(isinstance(u.get(k),int) for k in aggregate):raise RuntimeError('terminal usage missing')
  assert u['completion_tokens']<=remaining,'max_tokens semantics mismatch'
  for k in aggregate:aggregate[k]+=u[k]
  remaining-=u['completion_tokens'];calls=message.get('tool_calls') or []
  entry={'index':turn+1,'elapsed_s':time.monotonic()-at,'content':content,'reasoning_chars':len(message.get('reasoning_content') or ''),'tool_calls':calls,'usage':u,'finish_reason':choice.get('finish_reason'),'timings':data.get('timings'),'returned_model':data.get('model')}
  record['turns'].append(entry);record.update(content=content,usage=aggregate,elapsed_s=time.monotonic()-started);save()
  if not calls:record['usage_complete']=True;break
  if sim is None:raise RuntimeError('unexpected tool call')
  messages.append(message)
  for call in calls:
   try:args=json.loads(call['function']['arguments'])
   except (ValueError,KeyError):args={}
   result=sim.invoke(call['function']['name'],args);messages.append({'role':'tool','tool_call_id':call['id'],'content':json.dumps(result,ensure_ascii=False)})
 else:raise RuntimeError('agent_turn_limit')
except Exception as exc:
 record['error']=type(exc).__name__+': '+str(exc)
 if isinstance(exc,urllib.error.HTTPError):record['error_body']=exc.read(4096).decode(errors='replace')
record.update(content=content,usage=aggregate,elapsed_s=time.monotonic()-started)
if sim:record['tool_trace']=sim.trace
if record.get('error'):record['grade']={'pass':False,'error':record['error']}
elif a.kind=='preflight' and a.case=='O01':record['grade']={'pass':content.strip()=='1591','thinking_off_verified':record['turns'][0]['reasoning_chars']==0}
elif a.kind in ['main','preflight']:record['grade']=sim.grade(content) if sim else grade(task,content,folder)
elif a.kind=='thinking':
 try:
  if 'expected_text' in task:passed=content.strip()==task['expected_text']
  else:
   value=json.loads(content);expected=task['expected_json'];passed=isinstance(value,dict) and set(value)==set(expected) and all(type(value[k]) is type(v) and value[k]==v for k,v in expected.items())
 except (ValueError,TypeError,KeyError):passed=False
 record['grade']={'pass':passed}
else:record['grade']={'full_512_output':aggregate['completion_tokens']==512}
save();(folder/'answer.txt').write_text(content,encoding='utf-8')
print(json.dumps({k:record.get(k) for k in ['profile','kind','case','round','elapsed_s','usage','usage_complete','grade','error']},ensure_ascii=False),flush=True)
