"""Restricted pure-function checker. No imports/files/network in submitted code."""
import ast
import builtins
import copy
import json
import sys
from pathlib import Path

SAFE={k:getattr(builtins,k) for k in ['abs','all','any','bool','dict','enumerate','Exception','float','int','isinstance','len','list','max','min','range','reversed','round','set','sorted','str','sum','tuple','ValueError','zip','type','next','iter']}
ATTRS={'get','items','keys','values','append','add','discard','remove','pop','copy','update','setdefault','sort','clear','extend','count','index','split','strip','lower','upper','startswith','endswith','join','replace','isdigit','issubset','issuperset','difference','intersection','union'}

def tests(task):
    if task=='C01':
        return 'invoice_total',[
            (([],),0), (([{'status':'paid','qty':2,'unit_cents':199}],),398),
            (([{'status':'draft','qty':8,'unit_cents':1},{'status':'paid','qty':0,'unit_cents':20}],),0),
            (([{'status':'paid','qty':True,'unit_cents':99},{'status':'paid','qty':1,'unit_cents':False}],),0),
            (([{'status':'paid','qty':-1,'unit_cents':3},{'status':'paid','qty':1,'unit_cents':-3}],),0),
            (([None,7,[],{},'paid',{'status':'paid','qty':'2','unit_cents':3}],),0),
            (([{'status':'paid','qty':2.0,'unit_cents':3},{'status':'paid','qty':1,'unit_cents':3.0}],),0),
            (([{'status':'PAID','qty':1,'unit_cents':9},{'status':'paid','qty':3,'unit_cents':7}],),21),
            (([{'status':'paid','qty':10**8,'unit_cents':10**9}],),10**17)]
    if task=='C02':
        def e(i,a,d,t='2026-01-01'):return dict(event_id=i,account=a,delta_cents=d,ts=t)
        def v(a,b,n):return dict(account=a,balance_cents=b,event_count=n)
        return 'reconcile',[
            (([],),[]), (([e('1','a',4)],),[v('a',4,1)]),
            (([e('1','a',4),e('1','a',999,'2026-02-01')],),[v('a',4,1)]),
            (([e('1','z',4),e('2','a',8)],),[v('a',8,1),v('z',4,1)]),
            (([e('1','a',4),e('2','a',-4)],),[v('a',0,2)]),
            (([e('1','b',9),e('1','a',8)],),[v('b',9,1)]),
            (([e('1','a',-7),e('2','a',2),e('3','a',0)],),[v('a',-5,3)]),
            (([e('b','a',5,'2025-01-01'),e('a','a',-2,'2024-01-01')],),[v('a',3,2)])]
    def t(i,d,u=1,deps=()):return dict(id=i,duration=d,units=u,deps=list(deps))
    def r(j,m):return dict(jobs=[dict(id=i,start=s,end=e) for i,s,e in j],makespan=m)
    return 'schedule',[
        (([],2),r([],0)), (([t('a',3)],1),r([('a',0,3)],3)),
        (([t('b',2),t('a',3)],2),r([('a',0,3),('b',0,2)],3)),
        (([t('b',2),t('a',3)],1),r([('a',0,3),('b',3,5)],5)),
        (([t('a',3),t('b',2,deps=['a'])],2),r([('a',0,3),('b',3,5)],5)),
        (([t('a',4,2),t('b',2,2),t('c',1,1)],3),r([('a',0,4),('b',4,6),('c',0,1)],6)),
        (([t('a',2),t('b',2),t('c',1,2,['a','b'])],2),r([('a',0,2),('b',0,2),('c',2,3)],3)),
        (([t('z',2),t('a',1,deps=['z']),t('b',1,deps=['a'])],2),r([('a',2,3),('b',3,4),('z',0,2)],4)),
        (([t('a',1,3)],2),'ValueError'),
        (([t('a',1,deps=['missing'])],2),'ValueError'),
        (([t('a',1,deps=['b']),t('b',1,deps=['a'])],2),'ValueError'),
        (([t('a',1,deps=['a'])],2),'ValueError'),
        (([t('a',1),t('b',1,deps=['c']),t('c',1,deps=['b'])],2),'ValueError')]

def grade(task,code):
    if code.strip().startswith('```'):
        code='\n'.join(code.strip().splitlines()[1:-1])
    tree=ast.parse(code)
    names={n.name for n in ast.walk(tree) if isinstance(n,ast.FunctionDef)}
    for n in ast.walk(tree):
        if isinstance(n,(ast.Import,ast.ImportFrom,ast.ClassDef,ast.Global,ast.Nonlocal,ast.With,ast.AsyncFunctionDef)):
            raise ValueError('unsafe or unsupported syntax')
        if isinstance(n,ast.Name) and n.id.startswith('__'):
            raise ValueError('private namespace access')
        if isinstance(n,ast.Attribute) and n.attr not in ATTRS:
            raise ValueError('attribute not allowed: '+n.attr)
        if isinstance(n,ast.Call):
            if isinstance(n.func,ast.Name) and n.func.id=='type' and len(n.args)!=1:
                raise ValueError('dynamic type construction not allowed')
            if isinstance(n.func,ast.Name) and n.func.id not in SAFE and n.func.id not in names:
                raise ValueError('call not allowed: '+n.func.id)
            if not isinstance(n.func,(ast.Name,ast.Attribute)):
                raise ValueError('dynamic call not allowed')
    env={'__builtins__':SAFE}
    exec(compile(tree,'<submission>','exec'),env,env)
    fn,cases=tests(task)
    outcomes=[]
    for i,(args,expected) in enumerate(cases,1):
        args=copy.deepcopy(args);before=copy.deepcopy(args)
        try: actual=env[fn](*args)
        except ValueError: actual='ValueError'
        except Exception as exc: actual={'exception':type(exc).__name__}
        passed=actual==expected and args==before
        outcomes.append({'test':i,'pass':passed,'actual':actual,'expected':expected,'input_unchanged':args==before})
    return {'score':round(100*sum(x['pass'] for x in outcomes)/len(outcomes),2),'pass':all(x['pass'] for x in outcomes),'tests':outcomes}

if __name__=='__main__':
    try: answer=grade(sys.argv[1],Path(sys.argv[2]).read_text(encoding='utf-8'))
    except Exception as exc: answer={'score':0,'pass':False,'error':type(exc).__name__+': '+str(exc)}
    print(json.dumps(answer,ensure_ascii=False))
