"""Independent LC hard acceptance. Editorial memo review remains separate."""
import json
from corpus import EXPECTED
def grade(task,text):
 checks={}
 try:d=json.loads(text);assert isinstance(d,dict)
 except Exception:return {'pass':False,'checks':{'strict_json_object':False},'passed':0,'total':1}
 checks['strict_json_object']=True
 if task=='LC01':
  checks['exact_top_level_keys']=set(d)==set(EXPECTED)
  checks['policy']=d.get('policy_version')=='v2' and type(d.get('limit_cents')) is int and d.get('limit_cents')==30000
  got=d.get('decisions',[]);checks['ordered_four_decisions']=isinstance(got,list) and [x.get('order_id') for x in got if isinstance(x,dict)]==['O-A','O-B','O-C','O-D']
  for ref in EXPECTED['decisions']:
   item=next((x for x in got if isinstance(x,dict) and x.get('order_id')==ref['order_id']),{}) if isinstance(got,list) else {}
   checks[ref['order_id']+'_fields']=set(item)==set(ref)
   checks[ref['order_id']+'_net_and_route']=type(item.get('net_cents')) is int and item.get('net_cents')==ref['net_cents'] and item.get('route')==ref['route']
   ev=item.get('evidence',[]);allowed=set(ref['evidence'])|{'P-V1','P-V2','P-V3-DRAFT','P-RULE'}
   checks[ref['order_id']+'_evidence']=isinstance(ev,list) and all(isinstance(x,str) for x in ev) and set(ref['evidence'])<=set(ev)<=allowed
  ev=d.get('ignored',[]);checks['excluded_three_distractors']=isinstance(ev,list) and all(isinstance(x,str) for x in ev) and set(ev)==set(EXPECTED['ignored'])
 else:
  checks['exact_top_level_keys']=set(d)=={'approved_policy','total_requested_cents','auto_ids','manual_ids','rejected_ids','evidence_ids','memo'}
  checks['policy_and_amount']=d.get('approved_policy')=='v2' and type(d.get('total_requested_cents')) is int and d.get('total_requested_cents')==90000
  checks['auto']=d.get('auto_ids')==['O-A'];checks['manual']=d.get('manual_ids')==['O-B'];checks['reject']=d.get('rejected_ids')==['O-C','O-D']
  ev=d.get('evidence_ids',[]);checks['evidence']=isinstance(ev,list) and all(isinstance(x,str) for x in ev) and {'P-V2','P-V3-DRAFT','C-REFUND','D-STATE'}<=set(ev)
  memo=d.get('memo','');checks['memo_length']=isinstance(memo,str) and 160<=len(''.join(memo.split()))<=260
  checks['memo_mentions_orders']=isinstance(memo,str) and all(x in memo for x in ['O-A','O-B','O-C','O-D'])
 return {'pass':all(checks.values()),'checks':checks,'passed':sum(checks.values()),'total':len(checks),'editorial_required':task=='LC02'}
