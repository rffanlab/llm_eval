"""Opt-in API telemetry only; do not change generation or inference binary."""
from pathlib import Path
import ast,json,os,types,uuid,time,hashlib,sys
src=Path(sys.argv[1])
old=src.read_text(encoding='utf-8')
needle='            if x.get("timings"):\n                last["timings"] = x["timings"]'
addition='            if os.environ.get("STRATA_EVAL_REASONING_USAGE") == "1" and isinstance(x.get("reasoning_tokens"), int):\n                last["usage"]["completion_tokens_details"] = {"reasoning_tokens": x["reasoning_tokens"]}\n'
assert old.count(needle)==1,'source drift; do not patch'
new=old.replace(needle,addition+needle)
def isolated(code):
    tree=ast.parse(code)
    funcs=[n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name in ['openai_chunks','openai_collect','_is_json']]
    space={'os':os,'json':json,'uuid':uuid,'time':time,'Service':object,'Event':object}
    exec(compile(ast.Module(body=funcs,type_ignores=[]),'<serializer>','exec'),space)
    svc=types.SimpleNamespace(model_for=lambda req:'fixture-model')
    ev=[('event',types.SimpleNamespace(kind='reasoning',text='think')),('event',types.SimpleNamespace(kind='content',text='done')),('event',types.SimpleNamespace(kind='tool_call',call=types.SimpleNamespace(id='t1',name='read',arguments={'x':1}))),('done',{'finish':'stop','prompt_tokens':12,'completion_tokens':8,'reasoning_tokens':3,'reused':2,'timings':{'predicted_n':8}})]
    result=space['openai_collect'](space['openai_chunks'](svc,{},[1],True,None,20,None,run=ev))
    result.pop('id');result.pop('created')
    return result
os.environ.pop('STRATA_EVAL_REASONING_USAGE',None)
before=isolated(old)
assert isolated(new)==before
os.environ['STRATA_EVAL_REASONING_USAGE']='1'
after=isolated(new)
assert after['usage'].pop('completion_tokens_details')=={'reasoning_tokens':3}
assert after==before
backup=src.with_suffix('.py.original-eval')
assert not backup.exists(),'preserve original source'
backup.write_text(old,encoding='utf-8')
src.write_text(new,encoding='utf-8')
print(json.dumps({'contract':'same content, reasoning, tool calls, timings and usage, except opt-in existing reasoning count','original_sha256':hashlib.sha256(old.encode()).hexdigest(),'instrumented_sha256':hashlib.sha256(new.encode()).hexdigest(),'passed':True},indent=2))
