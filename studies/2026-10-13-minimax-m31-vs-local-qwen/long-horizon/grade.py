"""Independent pure-function oracle. No model endpoint calls."""
import ast,csv,io,json,os,subprocess,sys,types
from pathlib import Path
from fixture import BASE_O,BASE_R,V2_O,V2_R,FINAL_R,CUTOFF,expected

SAFE={'csv':['DictReader','DictWriter','reader','writer','QUOTE_MINIMAL'], 'io':['StringIO'], 'json':['loads','dumps'], 'decimal':['Decimal','ROUND_HALF_UP','InvalidOperation'], 'hashlib':['sha256'], 'collections':['defaultdict','Counter','OrderedDict'], 'datetime':['datetime','date','timezone'], 'math':['isfinite','floor','ceil']}
DENY={'open','exec','eval','compile','globals','locals','vars','getattr','setattr','delattr','__import__','input','breakpoint','help','exit','quit','type','object','memoryview'}
def load(source):
    tree=ast.parse(source)
    for node in ast.walk(tree):
        if isinstance(node,ast.Name) and (node.id in DENY or node.id.startswith('__')):raise ValueError('forbidden name '+node.id)
        if isinstance(node,ast.Attribute) and node.attr.startswith('__'):raise ValueError('private attribute denied')
        if isinstance(node,(ast.ClassDef,ast.AsyncFunctionDef,ast.Global,ast.Nonlocal)):raise ValueError('unsupported syntax')
        if isinstance(node,ast.Import) and any(n.name not in SAFE for n in node.names):raise ValueError('import denied')
        if isinstance(node,ast.ImportFrom) and (node.module not in SAFE or node.level or any(n.name not in SAFE[node.module] for n in node.names)):raise ValueError('from import denied')
    def importing(name,globals=None,locals=None,fromlist=(),level=0):
        # C datetime methods import these standard-library helpers internally.
        # Explicit model imports still pass the AST allowlist above.
        if name in ['_strptime','time'] and not level:return __import__(name)
        if name not in SAFE or level:raise ImportError('import denied')
        module=__import__(name)
        return types.SimpleNamespace(**{k:getattr(module,k) for k in SAFE[name]})
    import builtins
    names=['str','int','float','bool','list','dict','set','tuple','len','sum','min','max','sorted','range','enumerate','zip','any','all','abs','round','reversed','isinstance','Exception','ValueError','TypeError','KeyError','IndexError','RuntimeError','StopIteration','map','filter','next']
    env={'__builtins__':{k:getattr(builtins,k) for k in names},'__name__':'workflow'}
    env['__builtins__']['__import__']=importing
    exec(compile(tree,'workflow.py','exec'),env)
    return env

def cases(stage):
    cases=[]
    def add(name,o,r,p='v1',cut=None,want=None,error=False,visible=False):cases.append(dict(name=name,o=o,r=r,p=p,cut=cut,want=want,error=error,visible=visible))
    add('base_exact',BASE_O,BASE_R,want=expected('base'),visible=True)
    add('base_row_order', '\n'.join([BASE_O.splitlines()[0]]+BASE_O.splitlines()[1:][::-1])+'\n',BASE_R,want=expected('base'))
    emptyO=BASE_O.splitlines()[0]+'\n';emptyR=BASE_R.splitlines()[0]+'\n';zero={'orders':[],'customers':[],'totals':{'paid_cents':0,'refund_cents':0,'net_cents':0}}
    add('empty',emptyO,emptyR,want=zero,visible=True)
    for label,amount in [('negative','-1.00'),('precision','1.005'),('nan','NaN'),('infinity','Infinity')]:add('v1_'+label,BASE_O.replace('10.10',amount),BASE_R,error=True,visible=label=='precision')
    add('order_duplicate_conflict',BASE_O+'O01,A,11.10,paid,2026-10-01T10:00:00Z\n',BASE_R,error=True,visible=True)
    add('refund_duplicate_conflict',BASE_O,BASE_R+'R01,O01,2.11\n',error=True)
    add('unknown_refund',BASE_O,emptyR+'R99,O99,1.00\n',error=True,visible=True)
    add('cancelled_refund',BASE_O,emptyR+'R99,O03,1.00\n',error=True)
    add('excess_refund',BASE_O,emptyR+'R99,O01,10.11\n',error=True)
    one='order_id,customer,amount,status,created_at\nZ,z,0.29,paid,2026-10-01T00:00:00Z\n';rr='refund_id,order_id,amount\nX,Z,0.29\n';want={'orders':[{'order_id':'Z','customer':'z','paid_cents':29,'refund_cents':29,'net_cents':0}],'customers':[{'customer':'z','net_cents':0}],'totals':{'paid_cents':29,'refund_cents':29,'net_cents':0}}
    add('zero_customer_decimal',one,rr,want=want)
    add('policy_invalid',BASE_O,BASE_R,p='v9',error=True)
    if stage>=2:
        add('v2_exact',V2_O,V2_R,'v2',CUTOFF,expected('v2'),visible=True)
        add('v2_final',V2_O,FINAL_R,'v2',CUTOFF,expected('final'))
        add('v2_cutoff_missing',V2_O,V2_R,'v2',error=True,visible=True)
        add('v2_conflict_pending',V2_O,V2_R+'R02,O02,1.21,pending,2026-10-03T10:00:00Z\n','v2',CUTOFF,error=True)
        add('v2_future_order_refund',V2_O,V2_R+'R77,O05,2.00,succeeded,2026-10-04T10:00:00Z\n','v2',CUTOFF,expected('v2'))
        add('v2_unknown_active',V2_O,V2_R+'R77,X,2.00,succeeded,2026-10-04T10:00:00Z\n','v2',CUTOFF,error=True)
        add('v2_cancelled_active',V2_O,V2_R+'R77,O03,2.00,succeeded,2026-10-04T10:00:00Z\n','v2',CUTOFF,error=True)
        add('v2_excess',V2_O,V2_R+'R77,O01,8.01,succeeded,2026-10-04T10:00:00Z\n','v2',CUTOFF,error=True)
        add('v2_row_order', '\n'.join([V2_O.splitlines()[0]]+V2_O.splitlines()[1:][::-1])+'\n', '\n'.join([V2_R.splitlines()[0]]+V2_R.splitlines()[1:][::-1])+'\n','v2',CUTOFF,expected('v2'))
        add('v2_negative',V2_O.replace('10.105','-10.105'),V2_R,'v2',CUTOFF,error=True)
        # Inclusive boundary, round each item first: 0.005 -> 1 cent, twice -> 2 cents.
        oo='order_id,customer,amount,status,created_at\nA,Z,0.005,paid,'+CUTOFF+'\nB,Z,0.005,paid,'+CUTOFF+'\n';er=V2_R.splitlines()[0]+'\n'
        want={'orders':[{'order_id':'A','customer':'Z','paid_cents':1,'refund_cents':0,'net_cents':1},{'order_id':'B','customer':'Z','paid_cents':1,'refund_cents':0,'net_cents':1}], 'customers':[{'customer':'Z','net_cents':2}],'totals':{'paid_cents':2,'refund_cents':0,'net_cents':2}}
        add('v2_inclusive_round_each',oo,er,'v2',CUTOFF,want,visible=True)
    return cases

def suite(source,stage,visible=False):
    try:env=load(source)
    except Exception as e:return {'checks':[{'name':'code_load','pass':False,'detail':str(e)}],'pass':False}
    rows=[]
    for c in cases(stage):
        if visible and not c['visible']:continue
        try:
            value=env['reconcile'](c['o'],c['r'],policy=c['p'],cutoff=c['cut'])
            ok=not c['error'] and value==c['want'] and all(isinstance(x,int) and not isinstance(x,bool) for x in value['totals'].values())
            detail={'actual':value,'expected':c['want']} if not ok else None
        except Exception as e:ok=c['error'] and isinstance(e,ValueError);detail=None if ok else str(e)
        rows.append({'name':c['name'],'pass':ok,**({'detail':detail} if detail is not None else {})})
    return {'checks':rows,'pass':all(x['pass'] for x in rows)}

def bundle_grade(bundle,result):
    rows=[]
    def add(name,ok):rows.append({'name':name,'pass':bool(ok)})
    add('bundle_names',set(bundle)=={'orders.csv','customers.csv','summary.json'} and all(isinstance(x,str) for x in bundle.values()))
    try:
        add('summary_exact',json.loads(bundle['summary.json'])==result['totals'])
        for f,key,headers in [('orders.csv','orders',['order_id','customer','paid_cents','refund_cents','net_cents']),('customers.csv','customers',['customer','net_cents'])]:
            reader=csv.DictReader(io.StringIO(bundle[f]));records=list(reader);add(f+'_header',reader.fieldnames==headers)
            want=[{k:str(v) for k,v in row.items()} for row in result[key]];add(f+'_rows',records==want)
    except Exception:add('bundle_parse',False)
    return {'checks':rows,'pass':all(x['pass'] for x in rows)}

def worker(req):
    if sys.platform!='win32':
        import resource
        resource.setrlimit(resource.RLIMIT_CPU,(3,3));resource.setrlimit(resource.RLIMIT_AS,(512*2**20,512*2**20))
    if req['action']=='test':return suite(req['source'],req['stage'],req.get('visible',False))
    env=load(req['source']);ds=req['dataset'];o,r=(BASE_O,BASE_R) if ds=='base' else (V2_O,FINAL_R if ds=='final' else V2_R)
    result=env['reconcile'](o,r,policy='v1' if ds=='base' else 'v2',cutoff=None if ds=='base' else CUTOFF)
    if req['action']=='reconcile':return {'result':result}
    bundle=env['export_bundle'](result)
    return {'result':result,'bundle':bundle,'grade':bundle_grade(bundle,expected(ds))}

def isolated(source,action='test',stage=1,visible=False,dataset='v2'):
    req=dict(source=source,action=action,stage=stage,visible=visible,dataset=dataset)
    try:
        p=subprocess.run([sys.executable,str(Path(__file__).resolve()),'--worker'],input=json.dumps(req),text=True,capture_output=True,timeout=6,env={'PATH':os.defpath,'PYTHONUTF8':'1','PYTHONIOENCODING':'utf-8',**({k:os.environ[k] for k in ['SystemRoot','TEMP','TMP'] if k in os.environ})})
        if p.returncode:raise RuntimeError(p.stderr[-400:] or 'worker failed')
        return json.loads(p.stdout)
    except Exception as e:return {'error':str(e),'pass':False,'checks':[{'name':'worker','pass':False,'detail':str(e)}]}

def report_grade(text,published,events):
    import re
    rows=[]
    def add(name,ok):rows.append({'name':name,'pass':bool(ok)})
    add('length_400_900',400<=len(re.sub(r'\s','',text))<=900)
    from decimal import Decimal
    amounts={Decimal(x) for x in re.findall(r'(?<![A-Za-z\d])\d+\.\d+(?!\d)',text)}
    for amount,label in [('40.21','paid'),('5.51','refund'),('34.70','net'),('24.80','customer_A'),('9.90','customer_B'),('3.40','late_refund')]:add('fact_'+label,Decimal(amount) in amounts)
    add('cutoff_and_exclusions',all(x in text for x in [CUTOFF,'O05','R02','R03','R04']))
    add('sources',all(x in text for x in ['data/final/refunds.csv','release/summary.json']))
    add('compatibility','v1' in text.lower())
    add('actual_test_evidence',any(x['tool']=='run_tests' for x in events) and ('测试' in text or '回归' in text))
    add('failure_recovery',any(x['result'].get('error')=='ENOSPC_INJECTED' for x in events) and any(x['tool']=='publish' and x['result'].get('published') for x in events) and ('故障' in text or '失败' in text))
    add('no_hidden_pass_claim',not any(re.search(r'隐藏.*(?:全部|全数|均).*通过',clause) and not re.search(r'不声称|未声称|不能声称|不宣称|未宣称|不会声称|未通过|没有通过',clause) for clause in re.split(r'[。；\n]',text)))
    add('final_release_exact',published.get('dataset')=='final' and published.get('result')==expected('final'))
    return {'checks':rows,'pass':all(x['pass'] for x in rows),'provenance':'automatic factual/length checks; clarity and business risks need separate editorial review'}

if __name__=='__main__':
    try:out=worker(json.load(sys.stdin))
    except Exception as e:out={'error':str(e),'pass':False}
    print(json.dumps(out,ensure_ascii=False))
