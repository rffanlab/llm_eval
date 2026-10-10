"""One frozen local recording. Set LOCAL_BASE_URL, LOCAL_API_KEY and LOCAL_MODEL."""
import argparse,datetime,json,os,runpy,sys,time,urllib.request,urllib.error
from pathlib import Path
HERE=Path(__file__).resolve().parent;E=HERE.parents[1]
sys.path.insert(0,str(E))
p=argparse.ArgumentParser();p.add_argument('profile',choices=['next-flash-mtp','27b-dflash2','27b-ar'])
p.add_argument('kind',choices=['main','thinking','probe','repetition','capacity','timing'])
p.add_argument('--task');p.add_argument('--round',type=int,default=1);p.add_argument('--thinking',choices=['on','off'],default='on')
p.add_argument('--preflight',action='store_true');p.add_argument('--context');p.add_argument('--capacity-kind',choices=['retrieval','probe'])
p.add_argument('--fixture',choices=['small','medium','large']);p.add_argument('--repeat',choices=['new-prefix','exact-repeat'])
a=p.parse_args();assert all(os.environ.get(k) for k in ['LOCAL_BASE_URL','LOCAL_API_KEY','LOCAL_MODEL'])
if a.kind=='main':
 output=HERE/('preflight' if a.preflight else 'thinking-complex' if a.thinking=='off' else 'ar-quality-controls' if a.profile=='27b-ar' else 'results')/a.profile
 sys.argv=['runner.py','--provider','local','--profile',a.profile,'--study',str(HERE),'--suite',str(HERE/'tasks.json'),'--output',str(output),'--task',a.task,'--round',str(a.round),'--thinking',a.thinking,'--reasoning-effort','medium','--preserve-thinking','off','--presence-penalty','0']
 runpy.run_path(str(E/'runner.py'),run_name='__main__')
elif a.kind=='thinking':
 from overthinking_runner import run
 run(HERE,a.profile,a.task,a.thinking,a.round,'overthinking-native-tasks.json','overthinking-native','medium',False,0)
elif a.kind=='capacity':
 sys.argv=['capacity_runner.py','--study',str(HERE),'--profile',a.profile,'--context',a.context,'--kind',a.capacity_kind]
 runpy.run_path(str(HERE/'capacity_runner.py'),run_name='__main__')
else:
 stream=a.kind=='timing'
 if stream:
  fixture=next(x for x in json.loads((HERE/'timing-fixtures.json').read_text(encoding='utf-8')) if x['id']==a.fixture)
  target=HERE/'timing-probes'/a.profile/f'{a.fixture}-{a.repeat}.json'
  payload={'messages':fixture['messages'],'max_tokens':512,'stream':True,'stream_options':{'include_usage':True},'temperature':0}
 else:
  target=HERE/('preflight-probes' if a.preflight else 'repetition-probes' if a.kind=='repetition' else 'speed-probes')/a.profile/f'r{a.round}.json'
  payload=json.loads((HERE/('repetition-probe-prompt.json' if a.kind=='repetition' else 'speed-probe-prompt.json')).read_text(encoding='utf-8'))
 assert not target.exists(),'Never overwrite first attempts'
 payload.update(model=os.environ['LOCAL_MODEL'],reasoning_effort='none',presence_penalty=0,chat_template_kwargs={'enable_thinking':False,'reasoning_effort':'none','preserve_thinking':False})
 record={'profile':a.profile,'round':a.round,'kind':a.kind,'payload':payload,'started_at':datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=8))).isoformat()}
 if stream:record.update(fixture=a.fixture,repeat=a.repeat,first_content_delta_s=None,first_reasoning_delta_s=None,first_nonempty_delta_s=None,first_sse_chunk_s=None)
 began=time.monotonic()
 try:
  request=urllib.request.Request(os.environ['LOCAL_BASE_URL'].rstrip('/')+'/chat/completions',data=json.dumps(payload,ensure_ascii=False).encode(),headers={'Authorization':'Bearer '+os.environ['LOCAL_API_KEY'],'Content-Type':'application/json'})
  with urllib.request.urlopen(request,timeout=900 if stream else 240) as response:
   record['response_headers_s']=time.monotonic()-began
   record['server_timing_header']=response.headers.get('Server-Timing')
   if not stream:record['response']=json.load(response)
   else:
    chunks=[];answer=[];thought=[];usage=None;finished=None
    for raw in response:
     line=raw.decode('utf-8').strip()
     if not line.startswith('data:'):continue
     data=line[5:].strip()
     if data=='[DONE]':record['done_event']=True;break
     chunk=json.loads(data);at=time.monotonic()-began
     if record['first_sse_chunk_s'] is None:record['first_sse_chunk_s']=at
     chunks.append({'arrival_s':at,'data':chunk})
     if chunk.get('usage'):usage=chunk['usage']
     for choice in chunk.get('choices',[]):
      delta=choice.get('delta') or {}
      content=delta.get('content') or '';reasoning=delta.get('reasoning_content') or ''
      if content:
       answer.append(content)
       if record['first_content_delta_s'] is None:record['first_content_delta_s']=at
      if reasoning:
       thought.append(reasoning)
       if record['first_reasoning_delta_s'] is None:record['first_reasoning_delta_s']=at
      if (content or reasoning) and record['first_nonempty_delta_s'] is None:record['first_nonempty_delta_s']=at
      if choice.get('finish_reason') is not None:finished=choice['finish_reason']
    record.update(chunks=chunks,usage=usage,content=''.join(answer),reasoning_chars=len(''.join(thought)),finish_reason=finished)
    assert isinstance(usage,dict),'Terminal stream usage missing'
 except Exception as exc:
  record['error']=type(exc).__name__
  if isinstance(exc,urllib.error.HTTPError):record['http_status']=exc.code;record['error_body']=exc.read(8192).decode('utf-8',errors='replace')
 record['elapsed_s']=time.monotonic()-began
 usage=record.get('usage') if stream else record.get('response',{}).get('usage')
 record['full_512_output']=isinstance(usage,dict) and usage.get('completion_tokens')==512
 target.parent.mkdir(parents=True,exist_ok=True)
 target.write_text(json.dumps(record,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
 native=(usage or {}).get('gufo',{})
 print(json.dumps({'profile':a.profile,'kind':a.kind,'fixture':a.fixture,'repeat':a.repeat,'round':a.round,'elapsed_s':record['elapsed_s'],'full_512_output':record['full_512_output'],'first_content_s':record.get('first_content_delta_s'),'prefill_ms':native.get('prefill_ms'),'decode_ms':native.get('decode_ms'),'server_ttft_ms':native.get('ttft_ms'),'cache_tokens':(usage or {}).get('cached_tokens'),'error':record.get('error')},ensure_ascii=False),flush=True)
