"""Read an existing API with synchronized clients. No process/config/service mutations."""
import argparse
import concurrent.futures
import hashlib
import json
import math
import os
from pathlib import Path
import threading
import time
import urllib.error
import urllib.request

def save(path,data):
    with path.open('x',encoding='utf-8') as f:json.dump(data,f,ensure_ascii=False,indent=2)

def request_one(url,key,model,prompt,cap,barrier,submitted,timeout):
    payload={'model':model,'messages':prompt['messages'],'max_tokens':cap,'temperature':0,'seed':42,
             'reasoning_effort':'none','stream':True,'stream_options':{'include_usage':True}}
    headers={'Content-Type':'application/json'}
    if key:headers['Authorization']='Bearer '+key
    req=urllib.request.Request(url,data=json.dumps(payload,ensure_ascii=False).encode(),headers=headers)
    barrier.wait();start=time.perf_counter();result={'id':prompt['id'],'start_offset_s':start-submitted,
       'prompt':prompt,'first_token_s':None,'first_content_s':None,'usage':None,'raw_api_timings':None,
       'content':'','reasoning':'','finish_reason':None,'error':None}
    try:
        opener=urllib.request.build_opener(urllib.request.ProxyHandler({}))
        with opener.open(req,timeout=timeout) as response:
            for line in response:
                if not line.startswith(b'data:'):continue
                data=line[5:].strip()
                if data==b'[DONE]':break
                obj=json.loads(data)
                if obj.get('usage'):result['usage']=obj['usage']
                if obj.get('timings'):result['raw_api_timings']=obj['timings']
                for choice in obj.get('choices',[]):
                    if choice.get('finish_reason'):result['finish_reason']=choice['finish_reason']
                    delta=choice.get('delta',{})
                    content=delta.get('content');reason=delta.get('reasoning_content') or delta.get('reasoning')
                    now=time.perf_counter()-start
                    if isinstance(content,str) and content:
                        if result['first_content_s'] is None:result['first_content_s']=now
                        result['content']+=content
                    if isinstance(reason,str) and reason:result['reasoning']+=reason
                    # An empty role / keepalive event is deliberately excluded.
                    if result['first_token_s'] is None and ((isinstance(content,str) and content) or (isinstance(reason,str) and reason)):
                        result['first_token_s']=now
        if result['first_token_s'] is None:raise RuntimeError('No generated token in the stream')
        if result['usage'] is None:raise RuntimeError('Stream did not return usage; preserve this attempt')
    except Exception as exc:
        result['error']={'type':type(exc).__name__,'message':str(exc)[:300]}
    finish=time.perf_counter();result['elapsed_s']=finish-start;result['end_offset_s']=finish-submitted
    result['completion_is_quality_pass']=None
    return result

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--base-url',default=os.environ.get('EVAL_BASE_URL','http://127.0.0.1:8080/v1'))
    p.add_argument('--model',default='Qwen/Qwen3.8-Flash-Next');p.add_argument('--label',required=True)
    p.add_argument('--clients',type=int,choices=[1,2],required=True)
    p.add_argument('--prompts',type=Path,required=True);p.add_argument('--repeats',type=int,default=3)
    p.add_argument('--max-tokens',type=int,default=512);p.add_argument('--timeout',type=float,default=900)
    p.add_argument('--output',type=Path,required=True)
    a=p.parse_args();assert a.repeats>=1 and 1<=a.max_tokens<=8192
    assert not a.output.exists(),'Use a new output folder; preserve earlier attempts'
    prompts=json.loads(a.prompts.read_text(encoding='utf-8'));assert len(prompts)>=a.clients
    a.output.mkdir(parents=True)
    save(a.output/'inputs.json',{'label':a.label,'clients':a.clients,'model':a.model,'repeats':a.repeats,
       'max_tokens':a.max_tokens,'prompt_file_sha256':hashlib.sha256(a.prompts.read_bytes()).hexdigest(),
       'reasoning_effort':'none','quality_scope':'throughput probe only; run capability fixtures separately',
       'timing_scope':'API wall clock and raw reported timings; native fields need version-specific audit',
       'cache_scope':'No cache reset is performed. Preserve actual returned cached tokens and restart/cache policy externally.'})
    records=[]
    for n in range(1,a.repeats+1):
        barrier=threading.Barrier(a.clients+1);start=time.perf_counter()
        with concurrent.futures.ThreadPoolExecutor(max_workers=a.clients) as pool:
            jobs=[pool.submit(request_one,a.base_url.rstrip('/')+'/chat/completions',os.environ.get('EVAL_API_KEY',''),a.model,prompt,a.max_tokens,barrier,start,a.timeout) for prompt in prompts[:a.clients]]
            barrier.wait();rows=[job.result() for job in jobs]
        makespan=max(row['end_offset_s'] for row in rows)
        counts=[(row.get('usage') or {}).get('completion_tokens') for row in rows]
        valid=all(isinstance(x,int) and not isinstance(x,bool) and x>=0 for x in counts) and all(row['error'] is None for row in rows)
        first=[row['first_token_s'] for row in rows]
        report={'round':n,'clients':rows,'batch_elapsed_s':makespan,
         'batch_output_tokens':sum(counts) if valid else None,
         'batch_wall_output_tokens_s':sum(counts)/makespan if valid and makespan>0 else None,
         'last_first_token_s':max(row['start_offset_s']+row['first_token_s'] for row in rows) if all(x is not None for x in first) else None,
         'native_prefill_tokens_s':None,'native_decode_tokens_s':None,
         'native_note':'Never infer native times from these wall-clock measurements; audit raw_api_timings separately.'}
        save(a.output/f'round-{n}.json',report);records.append(report)
        print(json.dumps({'round':n,'errors':sum(r['error'] is not None for r in rows),'batch_elapsed_s':makespan}),flush=True)
    save(a.output/'complete.json',{'label':a.label,'rounds':len(records),'request_errors':sum(r['error'] is not None for x in records for r in x['clients']),
          'capability_quality_measured':False,'finished_epoch':time.time()})
if __name__=='__main__':main()
