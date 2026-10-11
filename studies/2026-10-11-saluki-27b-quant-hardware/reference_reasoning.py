"""Independent finite enumeration for the frozen R02 answer; never sent to models."""
import json,pathlib
feasible=[]
for a in range(13):
 for b in range(11):
  for c in range(16):
   machine=6*a+10*b+4*c;material=3*a+2*b+4*c
   if machine<=140 and material<=90:feasible.append({'A':a,'B':b,'C':c,'max_profit_yuan':17*a+23*b+15*c,'machine_time_used':machine,'material_used':material})
best=max(x['max_profit_yuan'] for x in feasible);optimal=[x for x in feasible if x['max_profit_yuan']==best]
reference=next(x['expected'] for x in json.loads(pathlib.Path(__file__).with_name('tasks.json').read_text(encoding='utf-8'))['tasks'] if x['id']=='R02')
assert len(optimal)==1 and optimal[0]==reference
print(json.dumps({'enumerated_candidates':13*11*16,'feasible_candidates':len(feasible),'unique_optimum':optimal[0]},ensure_ascii=False,indent=2))
