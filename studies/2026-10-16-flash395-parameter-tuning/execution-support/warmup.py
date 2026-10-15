"""Unscored D01 warmup in its own block directory; frozen graded inputs unchanged."""
import json,os,pathlib,subprocess,sys,time
R=pathlib.Path(os.environ['TUNE_ROOT']);S=R/'study';sys.path.insert(0,str(S));import runtime_controller as c
block=sys.argv[1];assert block in ['calibrate-medium-r1','calibrate-low-r1','calibrate-low-r2','calibrate-medium-r2','validate-base-r1','validate-selected-r1','validate-selected-r2','validate-base-r2']
c.quiet();c.guard();profile=c.current();cfg=c.config(profile);phase='warmup-'+block;label=phase+'-'+profile+'-short-D01-r1';j=R/'jobs'/(label+'.json');assert not j.exists()
env={**os.environ,'EVAL_PROFILE':profile,'EVAL_MODEL':'Qwen/Qwen3.8-Flash-Next','EVAL_BASE_URL':'http://127.0.0.1:'+str(c.PORT)+'/v1','EVAL_API_KEY':cfg['api_key'],'EVAL_SEED':'2026101601','EVAL_GUARD_COMMAND':json.dumps(['python3',str(S/'runtime_controller.py'),'guard']),'PYTHONUTF8':'1'}
cmd=['python3',str(S/'short_runner.py'),'--provider','local','--task','D01','--round','1','--output',str(R/'results'/phase/'short'/profile)]
with j.with_suffix('.log').open('w') as f:p=subprocess.Popen(['python3',str(S/'runtime_controller.py'),'worker',label,json.dumps(cmd)],env=env,stdout=f,stderr=f,start_new_session=True)
d={'label':label,'profile':profile,'phase':phase,'kind':'short','task':'D01','round':1,'pid':p.pid,'status':'running','start':time.time(),'quality_scored':False};c.save(j,d);print(json.dumps(d))
