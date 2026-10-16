"""Post-run aggregation. Reuse sealed baseline data; never performs inference or rescoring."""
from pathlib import Path
import csv
import hashlib
import importlib.util
import json

S=Path(__file__).resolve().parent
B=S.parent/'2026-10-15-strata-4060ti-vs-ai-max395'
PROFILES=['rtx4060ti','rx7900xtx','ai-max395']

def read(p):return json.loads(p.read_text(encoding='utf-8'))
def save(p,x):p.write_text(json.dumps(x,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def module(name,path):
    spec=importlib.util.spec_from_file_location(name,path);m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);return m

def main():
    for name,digest in read(S/'freeze.json')['files'].items():assert sha(S/name)==digest,name
    refs=read(S/'baseline-references.json')
    for name,row in refs['files'].items():assert sha(B/name)==row['sha256'],name
    baseline=read(B/'summary.json');assert baseline['complete_collection']
    m=module('baseline_summary',B/'summarize.py');m.HERE=S;m.PROFILES=['rx7900xtx'];m.main()
    rx=read(S/'summary.json');save(S/'summary-rx7900xtx.json',rx)
    combined={**rx,'profiles':{p:rx['profiles'][p] if p=='rx7900xtx' else baseline['profiles'][p] for p in PROFILES},
              'scope':'RX7900 XTX newly rerun on 2026-10-16 with power1_cap=261 W; RTX4060 Ti / AI Max+395 are sealed 2026-10-15 historical baselines. Two physical hosts; not all rerun together.',
              'rx7900xtx_power_cap_w':261,
              'power_condition_protocol':'power-condition-protocol.md',
              'baseline_references':'baseline-references.json','profile_sources':{p:'.' if p=='rx7900xtx' else '../'+B.name for p in PROFILES}}
    for p in ['rtx4060ti','ai-max395']:
        # Resolve preserved original results correctly from the extension directory.
        for task in combined['profiles'][p]['tasks'].values():
            for row in task['rounds']:row['source']='../'+B.name+'/'+row['source']
        for row in combined['profiles'][p]['depth']+combined['profiles'][p]['long_horizon']:row['source']='../'+B.name+'/'+row['source']
        for task in combined['profiles'][p]['speed'].values():
            for row in task['rounds']:row['source']='../'+B.name+'/'+row['source']
    combined['complete_collection']=all(x['complete_collection'] for x in combined['profiles'].values())
    save(S/'summary.json',combined)
    n=module('baseline_native',B/'aggregate_native_speeds.py');n.S=S;new=n.build();base_native=read(B/'native-speeds.json')
    merged={**new,'baseline_unique_formal_API_calls':base_native['unique_formal_API_calls'],
            'new_rx7900xtx_unique_formal_API_calls':new['unique_formal_API_calls'],
            'unique_formal_API_calls':base_native['unique_formal_API_calls']+new['unique_formal_API_calls'],
            'baseline_references':'baseline-references.json','groups':{}}
    for group,items in base_native['groups'].items():
        merged['groups'][group]={}
        for p in PROFILES:
            if p=='rx7900xtx':
                if p in new['groups'].get(group,{}):merged['groups'][group][p]=new['groups'][group][p]
                continue
            row=json.loads(json.dumps(items[p]))
            for rnd in row['rounds']:rnd['source']='../'+B.name+'/'+rnd['source']
            merged['groups'][group][p]=row
    save(S/'native-speeds.json',merged)
    rows=[]
    for group,ps in merged['groups'].items():
        for p,item in ps.items():
            for rnd in item['rounds']:
                rows.append(dict(group=group,profile=p,round=rnd['round'],source=rnd['source'],source_sha256=rnd['source_sha256'],**rnd['native_speed']))
    with (S/'native-speeds.csv').open('w',encoding='utf-8',newline='') as out:
        writer=csv.DictWriter(out,fieldnames=list(rows[0]));writer.writeheader();writer.writerows(rows)
    if combined['complete_collection']:
        assert len(rows)==105
        assert all(set(x)==set(PROFILES) for x in merged['groups'].values())
    print(json.dumps({'complete_collection':combined['complete_collection'],'new_unique_formal_API_calls':new['unique_formal_API_calls'],'aggregate_rows':len(rows),'main_delivery':{p:x['complete_main_deliveries'] for p,x in combined['profiles'].items()}},ensure_ascii=False))

if __name__=='__main__':main()
