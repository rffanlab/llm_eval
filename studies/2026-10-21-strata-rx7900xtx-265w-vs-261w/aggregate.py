"""Offline aggregation; model calls and raw evidence are never modified."""
from pathlib import Path
import importlib.util,json,hashlib,csv
S=Path(__file__).resolve().parent
B=S.parent/'2026-10-16-strata-rx7900xtx-261w'
LIB=S.parent/'2026-10-15-strata-4060ti-vs-ai-max395'
def read(p):return json.loads(p.read_text(encoding='utf-8'))
def save(p,x):p.write_text(json.dumps(x,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def main():
 for p,h in read(S/'freeze.json')['files'].items():assert sha(S/p)==h,p
 for p,x in read(S/'baseline-references.json')['files'].items():assert sha(B/p)==x['sha256'],p
 spec=importlib.util.spec_from_file_location('original_hardware_summary',LIB/'summarize.py');m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
 m.HERE=S;m.PROFILES=['rx7900xtx'];m.main()
 d=read(S/'summary.json');d.update(scope='Same host/model/deployment configuration: fresh265W2026-10-21 versus sealed historical261W2026-10-16. Same boot as earlier270W CE event; existingCE1 and soft-offline retained, no counter reset.',power_cap_w=265,historical_power_cap_w=261,preexisting_system_memory_corrected_ECC=1)
 save(S/'summary.json',d)
 base=read(B/'summary.json');combined={'study':S.name,'complete_collection':d['complete_collection'],'model':'Qwen3.8 Next Flash','quantization':'Unsloth UD-Q4_K_XL','engine':'Strata v0.1.44.1','conditions':{'261w':base['profiles']['rx7900xtx'],'265w':d['profiles']['rx7900xtx']},'dates':{'261w':'2026-10-16','265w':'2026-10-21'},'comparability':d['scope'],'speed_scope':'Per round sum native new-input/output tokens over matching compute seconds, then median; cache separate; no wall-time-derived rates.'}
 save(S/'comparison.json',combined)
 bn=read(B/'native-speeds.json')['groups'];nn=read(S/'native-speeds.json')['groups'];native={'unit':'token/s','scope':'Hardware power-cap conditions; same computation definition; stages and whole overlap, do not add.','groups':{}}
 rows=[]
 for group in sorted(set(bn)|set(nn)):
  native['groups'][group]={}
  for label,src in [('261w',bn),('265w',nn)]:
   item=src.get(group,{}).get('rx7900xtx');native['groups'][group][label]=item
   if not item:continue
   for rnd in item['rounds']:rows.append({'group':group,'condition':label,'round':rnd['round'],'source':('../'+B.name+'/' if label=='261w' else '')+rnd['source'],'source_sha256':rnd['source_sha256'],**rnd['native_speed']})
 save(S/'comparison-native-speeds.json',native)
 if rows:
  with (S/'comparison-native-speeds.csv').open('w',encoding='utf-8',newline='') as f:
   w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)
 print(json.dumps({'complete_collection':d['complete_collection'],'current_short_deliveries':combined['conditions']['265w']['complete_main_deliveries'],'baseline_short_deliveries':combined['conditions']['261w']['complete_main_deliveries'],'native_work_round_rows':len(rows)}))
if __name__=='__main__':main()
