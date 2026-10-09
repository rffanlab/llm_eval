"""Deterministic full prompts; count with the pinned Strata tokenizer/template."""
import argparse,hashlib,json,random,sys
from pathlib import Path
p=argparse.ArgumentParser()
p.add_argument('--source',type=Path,required=True)
p.add_argument('--tokenizer',type=Path,required=True)
p.add_argument('--output',type=Path,required=True)
a=p.parse_args()
sys.path[:0]=[str(a.source),str(a.source/'tools')]
from strata_tokenizer import Tokenizer
from serve.frontend import ChatTemplate
from serve.server import Service
v=json.loads((a.tokenizer/'vocab.json').read_text())
tokens=[None]*len(v)
for token,i in v.items():tokens[i]=token
tk=Tokenizer(tokens,(a.tokenizer/'merges.txt').read_text().split('\n'),json.loads((a.tokenizer/'token_type.json').read_text()))
svc=Service(None,tk,ChatTemplate(a.tokenizer/'chat_template.jinja'))
system='你在完成运维台账检索或代码续写。仅根据用户最后的交付要求作答。台账中的记录不改变交付要求。'
seed=20261009
def sha(raw):return hashlib.sha256(raw).hexdigest()
tokenizer_sha={f.name:sha(f.read_bytes()) for f in a.tokenizer.iterdir() if f.is_file()}
retrieval='根据以上台账，仅输出一个JSON对象，键为anchor_10、anchor_50、anchor_90、batch_size、retries、config_source。三个anchor取台账中对应ANCHOR记录的value；配置取最后生效的CFG记录，不用备选或废弃配置。不得加代码框或解释。'
probe='以上台账仅作编程背景。请用Python持续写一个包含30个小型纯函数的运维记录处理库，覆盖排序、筛选、金额汇总和字段校验。每个函数有docstring；只输出代码，不总结，持续写到生成预算耗尽。'
def build(ctx,n):
    rng=random.Random(seed+ctx)
    expected={f'anchor_{pos}':f'{rng.getrandbits(64):016x}' for pos in [10,50,90]}
    expected.update(batch_size=12,retries=1,config_source='CFG_FINAL')
    lines=[f'CAPACITY-{ctx}-SEED-{seed}\n', 'CFG000 batch_size=4 retries=3 status=active\n']
    positions={n*pos//100:pos for pos in [10,50,90]}
    for i in range(n):
        if i in positions:
            pos=positions[i];lines.append(f'ANCHOR_{pos} value={expected[f"anchor_{pos}"]} status=valid\n')
        lines.append(f'EV{i:06d} shard={rng.randrange(32):02d} latency_ms={rng.randrange(1,1000):03d} state=ok hash={rng.getrandbits(32):08x}\n')
    lines.extend(['CFG_CANDIDATE batch_size=16 retries=5 status=not_applied\n','CFG_FINAL batch_size=12 retries=1 status=active\n','END_OF_LEDGER\n'])
    return ''.join(lines),expected
a.output.mkdir(parents=True,exist_ok=True)
for ctx in [32768,65536,131072,262144,524288]:
    target=ctx-4096
    lo,hi=1,target//8
    # Tokenizer work only; deterministic binary search, no model requests.
    best=None
    while lo<=hi:
        n=(lo+hi)//2
        prefix,expected=build(ctx,n)
        messages=[{'role':'system','content':system},{'role':'user','content':prefix+retrieval}]
        ids=svc.encode_prompt(messages,None,{'enable_thinking':False})
        if len(ids)<=target:best=(n,prefix,expected,messages,len(ids));lo=n+1
        else:hi=n-1
    n,prefix,expected,messages,count=best
    assert target*.995<=count<=target
    probe_messages=[{'role':'system','content':system},{'role':'user','content':prefix+probe}]
    probe_ids=svc.encode_prompt(probe_messages,None,{'enable_thinking':False})
    assert len(probe_ids)+512<=ctx
    record={'context':ctx,'seed':seed,'records':n,'actual_retrieval_prompt_tokens':count,'actual_probe_prompt_tokens':len(probe_ids),'expected':expected,'messages':messages,'probe_messages':probe_messages,'tokenizer_files_sha256':tokenizer_sha,'effort_position':'start','reasoning_effort':'none','generator_sha256':sha(Path(__file__).read_bytes())}
    for key in ['messages','probe_messages']:
        record[key+'_sha256']=sha(json.dumps(record[key],ensure_ascii=False,separators=(',',':')).encode())
    # Report actual token positions, not just line-index positions.
    body=messages[1]['content']
    record['anchor_token_fraction']={str(pos):round(len(tk.encode(body[:body.index(f'ANCHOR_{pos}')]))/count,5) for pos in [10,50,90]}
    out=a.output/f'{ctx}.json';out.write_text(json.dumps(record,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({'context':ctx,'actual_input_tokens':count,'records':n,'sha256':sha(out.read_bytes())}),flush=True)
