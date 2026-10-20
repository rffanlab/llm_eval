"""Post-observation semantic annotation; raw exact acceptance is never changed.

Permitted lexical variants: v2/P-V2, optional literal 'DOC ' prefix on known
source IDs, and optional obsolete P-V1 in ignored. All money, decisions,
schemas and mandatory evidence remain exact. Registered after the MiniMax
captures and before inspecting official DeepSeek LC outputs.
"""
import json
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).parent/'long-context'))
from corpus import EXPECTED

def semantic_lc01(text):
 try:
  a=json.loads(text);assert isinstance(a,dict)
  checks={'schema':set(a)==set(EXPECTED),'policy':a.get('policy_version') in ['v2','P-V2'] and type(a.get('limit_cents')) is int and a['limit_cents']==30000}
  items=a.get('decisions');checks['order']=isinstance(items,list) and all(isinstance(x,dict) for x in items) and [x.get('order_id') for x in items]==['O-A','O-B','O-C','O-D']
  def norm_ids(x):
   assert isinstance(x,list) and all(isinstance(i,str) for i in x)
   return {i[4:] if i.startswith('DOC ') else i for i in x}
  for ref in EXPECTED['decisions']:
   item=next((x for x in items if isinstance(x,dict) and x.get('order_id')==ref['order_id']),{})
   checks[ref['order_id']+'_fields']=set(item)==set(ref)
   checks[ref['order_id']+'_decision']=type(item.get('net_cents')) is int and item['net_cents']==ref['net_cents'] and item.get('route')==ref['route']
   ev=norm_ids(item.get('evidence'));checks[ref['order_id']+'_evidence']=set(ref['evidence'])<=ev<=set(ref['evidence'])|{'P-V1','P-V2','P-V3-DRAFT','P-RULE'}
  ignored=norm_ids(a.get('ignored'));checks['ignored']={'P-V3-DRAFT','X-STAGING-A','X-LOG'}<=ignored<= {'P-V1','P-V3-DRAFT','X-STAGING-A','X-LOG'}
  return {'pass':all(checks.values()),'checks':checks,'annotation_only':True}
 except Exception:return {'pass':False,'checks':{'complete_parseable_answer':False},'annotation_only':True}
