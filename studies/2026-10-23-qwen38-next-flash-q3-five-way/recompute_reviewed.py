"""Recompute frozen metrics from published evidence; no network or model requests."""
import argparse,json
from pathlib import Path
from aggregate import analyze
p=argparse.ArgumentParser();p.add_argument('--output',type=Path,required=True);a=p.parse_args()
r=Path(__file__).resolve().parent
z=analyze(r/'results',json.loads((r/'editorial-reviewed.json').read_text(encoding='utf-8'))['reviews'])
expected=json.loads((r/'metrics-reviewed.json').read_text(encoding='utf-8'))
assert z==expected,'Recomputed metrics differ'
a.output.write_text(json.dumps(z,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
print('All recomputed fields match reviewed metrics.')
