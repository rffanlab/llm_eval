"""Local, serial API evidence with all native GEN legs; no calls before study freeze."""
from pathlib import Path
import hashlib
import json
import os
import socket
import time
import urllib.error
import urllib.parse
import urllib.request

import native_timing

ROOT=Path(__file__).resolve().parent


class CallFailed(RuntimeError):
    """A retained transport/runtime failure; not an intelligence score."""


def verify_freeze():
    frozen=json.loads((ROOT/'freeze.json').read_text(encoding='utf-8'))
    assert frozen['formal_requests_authorized_after_both_actual100K_admissions']
    for name,sha in frozen['files'].items():
        assert hashlib.sha256((ROOT/name).read_bytes()).hexdigest()==sha,('Frozen source changed',name)


def save(path,data):
    path.write_text(json.dumps(data,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')


def payload(provider,model,messages,limit,tools=None,low=False):
    assert provider=='local' and isinstance(limit,int) and limit>0
    out={'model':model,'messages':messages,'temperature':0,'seed':42,'stream':True,
         'stream_options':{'include_usage':True},'max_tokens':limit,
         'reasoning_effort':'none' if low else 'medium',
         'chat_template_kwargs':{'preserve_thinking':False},'cache_prompt':True}
    if not low:
        out['reasoning_budget_tokens']=limit-min(max(512,limit//4),limit//2)
    if tools:out.update(tools=tools,tool_choice='auto',parallel_tool_calls=False)
    return out


def history(provider,message):
    assert provider=='local'
    return {k:v for k,v in message.items() if k!='reasoning_content'}


class StreamAccumulator:
    """Collect actual delta events; a valid finish alone does not imply a complete stream."""
    def __init__(self):
        self.content='';self.reasoning='';self.tools={};self.usage={};self.model=None
        self.finish=None;self.timings=None;self.done=False
        self.latency={k:None for k in ['first_event_s','first_reasoning_s','first_content_s','first_tool_s']}

    def event(self,data,elapsed):
        if self.latency['first_event_s'] is None:self.latency['first_event_s']=elapsed
        if data.get('error'):raise CallFailed('API stream error: '+json.dumps(data['error'],ensure_ascii=False))
        self.model=data.get('model',self.model);self.usage=data.get('usage') or self.usage
        self.timings=data.get('timings') or self.timings
        for choice in data.get('choices',[]):
            if choice.get('index',0)!=0:continue
            delta=choice.get('delta') or choice.get('message') or {};full='message' in choice
            value=delta.get('content') or ''
            if value:
                if self.latency['first_content_s'] is None:self.latency['first_content_s']=elapsed
                self.content=value if full else self.content+value
            value=delta.get('reasoning_content') or ''
            if value:
                if self.latency['first_reasoning_s'] is None:self.latency['first_reasoning_s']=elapsed
                self.reasoning=value if full else self.reasoning+value
            for tool in delta.get('tool_calls') or []:
                if self.latency['first_tool_s'] is None:self.latency['first_tool_s']=elapsed
                target=self.tools.setdefault(tool.get('index',0),{'id':'','type':'function','function':{'name':'','arguments':''}})
                if tool.get('id'):target['id']=tool['id']
                for key in ['name','arguments']:
                    value=(tool.get('function') or {}).get(key)
                    if value:target['function'][key]=value if full else target['function'][key]+value
            self.finish=choice.get('finish_reason') or self.finish

    def response(self):
        msg={'role':'assistant','content':self.content}
        if self.reasoning:msg['reasoning_content']=self.reasoning
        if self.tools:msg['tool_calls']=[self.tools[i] for i in sorted(self.tools)]
        return {'model':self.model,'choices':[{'index':0,'message':msg,'finish_reason':self.finish}],
                'usage':self.usage,'timings':self.timings}


def capture_native(blob,before,after,api_success):
    """Native rate validity requires complete prefill, every GEN, and a unique metrics ID."""
    rows=native_timing.parse_interval(blob.decode('utf-8',errors='replace'))
    prior={x['id']:x for x in before.get('requests',[])}
    added=[x for x in after.get('requests',[]) if x['id'] not in prior]
    errors=[];metric=added[0] if len(added)==1 else None
    if len(added)!=1:errors.append('expected_exactly_one_new_metrics_request_ID')
    if not rows:errors.append('no_complete_native_GEN_summary')
    if rows and not all(x['prompt_complete'] for x in rows):errors.append('partial_native_prefill')
    if metric is not None and rows:
        if sum(x['generated'] for x in rows)!=metric.get('engine_generated'):errors.append('native_generated_mismatch')
        for row_key,metric_key in [('prompt_ms','prompt_ms'),('decode_ms','decode_ms')]:
            value=metric.get(metric_key)
            if not isinstance(value,(int,float)) or abs(sum(x[row_key] for x in rows)-value)>.51*len(rows):
                errors.append('native_'+row_key+'_mismatch')
    if not api_success:errors.append('API_not_complete_success')
    return {'capture_complete':not errors,'capture_errors':errors,'metrics_new_request':metric,
            'all_GEN_legs':rows,'native':native_timing.summarize(rows,complete_interval=not errors),
            'internal_prefix_reuse_tokens':[x['cache'] for x in rows[1:]],
            'metrics_drafts_offered':metric.get('drafts_offered') if metric else None,
            'metrics_drafts_accepted':metric.get('drafts_accepted') if metric else None}


def call(base,key,body,timeout,event_path):
    verify_freeze()
    event_path=Path(event_path)
    assert not event_path.exists(), 'Preserve the existing call; no overwrite or automatic retry'
    parsed=urllib.parse.urlsplit(base)
    assert parsed.scheme=='http' and parsed.hostname in ('127.0.0.1','localhost'),'This frozen transport is for the local evaluation service'
    log=Path(os.environ['EVAL_ENGINE_LOG']);initial=log.stat();start_byte=initial.st_size
    metrics_url=os.environ['EVAL_METRICS_URL']
    assert urllib.parse.urlsplit(metrics_url).netloc==parsed.netloc
    headers={'Content-Type':'application/json',**({'Authorization':'Bearer '+key} if key else {})}
    def metrics():
        req=urllib.request.Request(metrics_url,headers=headers)
        with urllib.request.urlopen(req,timeout=30) as response:return json.loads(response.read())
    stem=event_path.with_suffix('')
    before=metrics();save(Path(str(stem)+'.metrics-before.json'),before)
    assert (before.get('live') or {}).get('state') in (None,'idle'),'Concurrent API request is not admitted'
    request_bytes=json.dumps(body,ensure_ascii=False,separators=(',',':')).encode()
    Path(str(stem)+'.request.json').write_bytes(request_bytes)
    accumulator=StreamAccumulator();started=time.monotonic();deadline=started+timeout
    request=urllib.request.Request(base.rstrip('/')+'/chat/completions',data=request_bytes,headers=headers)
    error=None;status=None
    try:
        with event_path.open('x',encoding='utf-8') as events,Path(str(stem)+'.sse').open('xb') as wire:
            with urllib.request.urlopen(request,timeout=timeout) as response:
                status=response.status
                # The pinned Python3.12 HTTPResponse exposes the socket through its file.
                # Reset its timeout to the remaining whole-call budget before every line.
                transport_socket=getattr(getattr(response.fp,'raw',None),'_sock',None)
                if not isinstance(transport_socket,socket.socket):raise CallFailed('Cannot enforce the frozen whole-call deadline')
                while True:
                    remaining=deadline-time.monotonic()
                    if remaining<=0:raise CallFailed('whole_API_call_deadline_exceeded')
                    transport_socket.settimeout(remaining)
                    raw=response.readline()
                    if not raw:break
                    wire.write(raw);wire.flush()
                    line=raw.decode('utf-8').strip()
                    if not line.startswith('data:'):continue
                    text=line[5:].strip()
                    if text=='[DONE]':accumulator.done=True;break
                    data=json.loads(text);elapsed=time.monotonic()-started
                    if key and key in text:raise CallFailed('Credential echo retained privately; refuse public export')
                    events.write(json.dumps({'received_s':elapsed,'event':data},ensure_ascii=False)+'\n');events.flush()
                    accumulator.event(data,elapsed)
        if not accumulator.done:raise CallFailed('SSE ended without_DONE')
        if not accumulator.finish:raise CallFailed('SSE ended without_finish_reason')
        if not all(isinstance(accumulator.usage.get(k),int) and not isinstance(accumulator.usage.get(k),bool) for k in ['prompt_tokens','completion_tokens','total_tokens']):
            raise CallFailed('API usage missing; cumulative tokens remain unknown')
        if accumulator.usage['completion_tokens']>body['max_tokens']:raise CallFailed('API output budget was not enforced')
    except Exception as exc:
        error={'type':type(exc).__name__,'text':str(exc)}
        if isinstance(exc,urllib.error.HTTPError):
            status=exc.code
            Path(str(stem)+'.http-error.body').write_bytes(exc.read())
    api_complete_wall=time.monotonic()-started
    capture_started=time.monotonic();after={};native_result=None;capture_errors=[]
    try:
        after=metrics();save(Path(str(stem)+'.metrics-after.json'),after)
        for _ in range(31):
            current=log.stat()
            assert (current.st_dev,current.st_ino)==(initial.st_dev,initial.st_ino) and current.st_size>=start_byte,'Engine log changed identity'
            with log.open('rb') as handle:handle.seek(start_byte);blob=handle.read(current.st_size-start_byte)
            native_result=capture_native(blob,before,after,error is None)
            if native_result['capture_complete'] or time.monotonic()-capture_started>=3:break
            time.sleep(.1)
        Path(str(stem)+'.native.log').write_bytes(blob)
    except Exception as exc:capture_errors.append({'type':type(exc).__name__,'text':str(exc)})
    result=accumulator.response()
    timing={**accumulator.latency,'api_elapsed_s':api_complete_wall,'evidence_capture_s':time.monotonic()-capture_started,
            'HTTP_status':status,'SSE_DONE_seen':accumulator.done,'error':error,
            'engine_log_begin_byte':start_byte,'engine_log_end_byte':start_byte+len(blob) if 'blob' in locals() else None,
            'engine_log_device':initial.st_dev,'engine_log_inode':initial.st_ino,
            'request_SHA256':hashlib.sha256(request_bytes).hexdigest(),'native_capture':native_result,'capture_exceptions':capture_errors}
    save(Path(str(stem)+'.evidence.json'),{'response':result,'timing':timing})
    if error:raise CallFailed(error['type']+': '+error['text'])
    return result,timing
