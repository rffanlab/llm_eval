"""One streamed request; native timing and usage, never guesses missing metrics."""
import hashlib,json,pathlib,time,urllib.request,urllib.error

def verify_freeze():
    root=pathlib.Path(__file__).resolve().parent
    declared=json.loads((root/'freeze.json').read_text(encoding='utf-8'))['files']
    assert all(hashlib.sha256((root/name).read_bytes()).hexdigest()==sha for name,sha in declared.items()),'study source changed after freeze'

def call(base,key,payload,timeout,event_path):
    started=time.monotonic();latency={k:None for k in ['first_event_s','first_reasoning_s','first_content_s','first_tool_s']}
    headers={'Content-Type':'application/json'}
    if key:headers['Authorization']='Bearer '+key
    req=urllib.request.Request(base.rstrip('/')+'/chat/completions',data=json.dumps(payload,ensure_ascii=False).encode(),headers=headers)
    content='';reasoning='';tools={};usage={};model=None;finish=None;timings=None;last={}
    with event_path.open('w',encoding='utf-8') as evidence:
        try:
            with urllib.request.urlopen(req,timeout=timeout) as response:
                for raw in response:
                    line=raw.decode('utf-8').strip()
                    if not line.startswith('data:'):continue
                    text=line[5:].strip()
                    if text=='[DONE]':break
                    data=json.loads(text);elapsed=time.monotonic()-started
                    assert not key or key not in text,'credential echoed; stop and keep it private'
                    evidence.write(json.dumps({'received_s':elapsed,'event':data},ensure_ascii=False)+'\n');evidence.flush()
                    if latency['first_event_s'] is None:latency['first_event_s']=elapsed
                    if data.get('error'):raise RuntimeError('provider SSE error: '+json.dumps(data['error'],ensure_ascii=False))
                    status=data.get('base_resp',{})
                    if status.get('status_code',0):raise RuntimeError('provider status '+str(status['status_code'])+': '+status.get('status_msg','').replace(key,'[REDACTED]'))
                    model=data.get('model',model);usage=data.get('usage') or usage;timings=data.get('timings') or timings;last=data
                    for choice in data.get('choices',[]):
                        if choice.get('index',0)!=0:continue
                        delta=choice.get('delta') or choice.get('message') or {};is_full='message' in choice
                        value=delta.get('content') or ''
                        if value:
                            if latency['first_content_s'] is None:latency['first_content_s']=elapsed
                            content=value if is_full else content+value
                        value=delta.get('reasoning_content') or ''
                        if value:
                            if latency['first_reasoning_s'] is None:latency['first_reasoning_s']=elapsed
                            reasoning=value if is_full else reasoning+value
                        for tool in delta.get('tool_calls') or []:
                            if latency['first_tool_s'] is None:latency['first_tool_s']=elapsed
                            index=tool.get('index',0);target=tools.setdefault(index,{'id':'','type':'function','function':{'name':'','arguments':''}})
                            if tool.get('id'):target['id']=tool['id']
                            fn=tool.get('function') or {}
                            for k in ['name','arguments']:
                                if fn.get(k):target['function'][k]=fn[k] if is_full else target['function'][k]+fn[k]
                        finish=choice.get('finish_reason') or finish
        except urllib.error.HTTPError as error:
            detail=error.read().decode('utf-8','replace')
            if key:detail=detail.replace(key,'[REDACTED]')
            evidence.write(json.dumps({'http_error':error.code,'body':detail},ensure_ascii=False)+'\n')
            raise RuntimeError('HTTP '+str(error.code)) from None
        except urllib.error.URLError as error:raise RuntimeError('network '+type(error.reason).__name__) from None
    latency['api_elapsed_s']=time.monotonic()-started
    message={'role':'assistant','content':content}
    if reasoning:message['reasoning_content']=reasoning
    if tools:message['tool_calls']=[tools[i] for i in sorted(tools)]
    response={'model':model,'choices':[{'index':0,'message':message,'finish_reason':finish}],'usage':usage,'timings':timings}
    if last.get('base_resp'):response['base_resp']=last['base_resp']
    return response,latency

def payload(provider,model,messages,limit,tools=None,low=False):
    out={'model':model,'messages':messages,'temperature':0,'stream':True,'stream_options':{'include_usage':True}}
    if provider=='minimax':out.update(max_completion_tokens=limit,reasoning_effort='low' if low else 'max',reasoning_split=True)
    else:out.update(max_tokens=limit,reasoning_effort='low' if low else 'max',thinking={'type':'enabled'})
    if tools:out.update(tools=tools,tool_choice='auto',parallel_tool_calls=False)
    return out

def history(provider,message):
    # Preserve complete native assistant messages for both remote reasoning APIs.
    return message
