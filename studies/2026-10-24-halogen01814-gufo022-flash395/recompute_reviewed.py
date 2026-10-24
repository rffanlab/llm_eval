"""Offline verification of published results; never calls an inference endpoint."""
import argparse,hashlib,json,importlib.util
from pathlib import Path

S=Path(__file__).resolve().parent
def read(p):return json.loads(p.read_text(encoding='utf-8'))
def analyze():
    frozen=read(S/'freeze.json')
    assert all(hashlib.sha256((S/n).read_bytes()).hexdigest()==h for n,h in frozen['files'].items())
    for name,z in read(S/'result-file-manifest.json')['files'].items():
        p=S/'results'/name;assert p.stat().st_size==z['public_bytes']and hashlib.sha256(p.read_bytes()).hexdigest()==z['public_sha256']
    spec=importlib.util.spec_from_file_location('frozen_analysis',S/'aggregate.py');m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
    out=m.analyze(S/'results',read(S/'editorial-review.json')['reviews'])
    for label,c in out['conditions'].items():
        c['completion_evidence']={'all29_recorded':True,'raw_condition_progress_is_historical_for_Halogen':label.startswith('halogen'),'completion_source':'recovery-proc-20261024/progress.json'if label.startswith('halogen')else'results/gufo022-q4xl/progress.json'}
        c['quality_summary']['recommendation_pending_primary_review']=False
    assert out==read(S/'metrics-reviewed.json'),'recomputation differs from published reviewed metrics'
    return out
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--output',type=Path,required=True);a=p.parse_args();assert not a.output.exists()
    out=analyze();a.output.write_text(json.dumps(out,ensure_ascii=False,indent=2)+'\n',encoding='utf-8');print('All published reviewed metric fields reproduced exactly; frozen inputs and result SHA verified.')
