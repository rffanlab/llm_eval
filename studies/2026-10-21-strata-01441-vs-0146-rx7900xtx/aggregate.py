"""Aggregate preserved current-version and upgrade evidence without model calls."""
from pathlib import Path
import json,hashlib,importlib.util,csv
S=Path(__file__).resolve().parent
B=S.parent/'2026-10-21-strata-rx7900xtx-265w-vs-261w'
LIB=S.parent/'2026-10-15-strata-4060ti-vs-ai-max395'
def read(p):return json.loads(p.read_text(encoding='utf-8'))
def save(p,x):p.write_text(json.dumps(x,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def main():
 for p,h in read(S/'freeze.json')['files'].items():assert sha(S/p)==h,p
 for p,x in read(S/'baseline-references.json')['files'].items():assert sha(B/p)==x['sha256'],p
 spec=importlib.util.spec_from_file_location('original_hardware_summary',LIB/'summarize.py');m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);m.HERE=S;m.PROFILES=['rx7900xtx'];m.main()
 d=read(S/'summary.json');d.update(engine='Strata engine0.1.46 / Control0.1.46.3 / release0.2.1',scope='Same machine,265W,weights,explicit inference arguments and frozen tasks; latest official Linux RX7900 engine+frontend+bundled user libraries and matching tuning table, versus same-day current0.1.44.1 local build. Sequential, not randomized. Existing CE1 retained and unchanged baseline required.')
 save(S/'summary.json',d)
 base=read(B/'summary.json');combined={'study':S.name,'complete_collection':d['complete_collection'],'model':'Qwen3.8 Next Flash','quantization':'Unsloth UD-Q4_K_XL','power_cap_w':265,'conditions':{'old':base['profiles']['rx7900xtx'],'new':d['profiles']['rx7900xtx']},'versions':{'old':'engine0.1.44.1/local HIP build','new':'engine0.1.46/Control0.1.46.3/release0.2.1'},'comparability':d['scope'],'speed_scope':'Per round sum native new-input/output tokens over matching compute seconds, then median; cache separate; no wall-derived rates.'};save(S/'comparison.json',combined)
 bn=read(B/'native-speeds.json')['groups'];nn=read(S/'native-speeds.json')['groups'];native={'unit':'token/s','scope':'Strata version conditions; stages and whole overlap, do not add.','groups':{}};rows=[]
 for group in sorted(set(bn)|set(nn)):
  native['groups'][group]={}
  for label,src in [('old',bn),('new',nn)]:
   item=src.get(group,{}).get('rx7900xtx');native['groups'][group][label]=item
   if not item:continue
   for rnd in item['rounds']:rows.append({'group':group,'condition':label,'round':rnd['round'],'source':('../'+B.name+'/' if label=='old' else '')+rnd['source'],'source_sha256':rnd['source_sha256'],**rnd['native_speed']})
 save(S/'comparison-native-speeds.json',native)
 if rows:
  with (S/'comparison-native-speeds.csv').open('w',encoding='utf-8',newline='') as f:
   w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)
 print(json.dumps({'complete_collection':d['complete_collection'],'current_old_short_deliveries':combined['conditions']['old']['complete_main_deliveries'],'new_short_deliveries':combined['conditions']['new']['complete_main_deliveries'],'native_work_round_rows':len(rows)}))
if __name__=='__main__':main()
