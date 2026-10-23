"""Generate a private config copy; do not print it, launch a model, or overwrite files."""
import argparse
import json
from pathlib import Path

def patch(config,parallel,batch_mtp=None,prefill=None):
    result=dict(config);args=list(result.get('args',[]))
    if any(a in ['--batch','--slots'] or str(a).startswith(('--batch=','--slots=')) for a in args):
        raise ValueError('Explicit --batch/--slots in args overrides parallel; resolve it in a private base first')
    result['parallel']=parallel
    if batch_mtp is not None:
        args=[a for a in args if a!='--batch-mtp']
        if batch_mtp:args.append('--batch-mtp')
    if prefill is not None:
        cleaned=[];skip=False
        for a in args:
            if skip:skip=False;continue
            if a=='--prefill':skip=True;continue
            if str(a).startswith('--prefill='):continue
            cleaned.append(a)
        args=[*cleaned,'--prefill',str(prefill)]
    result['args']=args
    return result

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('base',type=Path);p.add_argument('--output',type=Path,required=True)
    p.add_argument('--parallel',type=int,choices=[1,2],required=True)
    g=p.add_mutually_exclusive_group();g.add_argument('--batch-mtp',dest='batch_mtp',action='store_true');g.add_argument('--no-batch-mtp',dest='batch_mtp',action='store_false')
    p.set_defaults(batch_mtp=None);p.add_argument('--prefill',type=int,choices=[1024,2048,4096,8192])
    a=p.parse_args();data=json.loads(a.base.read_text(encoding='utf-8-sig'))
    updated=patch(data,a.parallel,a.batch_mtp,a.prefill)
    with a.output.open('x',encoding='utf-8') as out:json.dump(updated,out,ensure_ascii=False,indent=2)
    print(json.dumps({'output_written':True,'parallel':a.parallel,'config_not_printed':True,'model_launched':False}))
if __name__=='__main__':main()
