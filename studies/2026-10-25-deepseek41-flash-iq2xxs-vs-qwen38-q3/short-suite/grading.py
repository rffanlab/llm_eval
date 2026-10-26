"""Frozen-compatible task grading functions; no API or credential code."""
import json,os,subprocess,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parent

def save(path,data):
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(data,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')

def grade(task,content,folder):
    if task['domain']=='code':
        file=folder/'submission.py';file.write_text(content,encoding='utf-8')
        try:
            p=subprocess.run([sys.executable,'-I',str(ROOT/'sandbox_grade.py'),task['id'],str(file)],capture_output=True,text=True,encoding='utf-8',timeout=5,env={'PATH':os.defpath,'PYTHONUTF8':'1','PYTHONIOENCODING':'utf-8'})
            return json.loads(p.stdout)
        except subprocess.TimeoutExpired:return {'score':0,'pass':False,'error':'execution_timeout_5s'}
        except Exception:return {'score':0,'pass':False,'error':'grader_process_error'}
    if task.get('expected') is not None:
        try:data=json.loads(content)
        except Exception:data={}
        if not isinstance(data,dict):data={}
        expected=task['expected'];checks={k:data.get(k)==v for k,v in expected.items()};checks['exact_keys']=set(data)==set(expected)
    else:
        c=task['checks'];length=len(''.join(content.split()))
        checks={'length':c['min_chars']<=length<=c['max_chars'],**{f'has_{s}':s in content for s in c['required']}}
        if 'paragraphs' in c:checks['paragraphs']=len([x for x in content.split('\n\n') if x.strip()])==c['paragraphs']
        return {'score':round(100*sum(checks.values())/len(checks),2),'pass':all(checks.values()),'checks':checks,'nonspace_chars':length,'editor_review_pending':True}
    return {'score':round(100*sum(checks.values())/len(checks),2),'pass':all(checks.values()),'checks':checks}
