"""One model, one manually initiated case. Private paths are supplied via environment."""
import hashlib,json,os,pathlib,secrets,subprocess,sys,time,urllib.request
P=pathlib.Path
R=P(os.environ['TUNE_ROOT']);S=R/'study';SOURCE=P(os.environ['TUNE_SOURCE']);OLD=P(os.environ['TUNE_PREVIOUS'])
UNIT='ai-flash395-tuning-20261016.service';PORT=8747
PROD=['ai-llm-router.service','ai-llm-gufo.service'];PROFILES=json.loads((S/'profiles.json').read_text())
def read(p):return json.loads(p.read_text())
def save(p,x):
 p.parent.mkdir(parents=True,exist_ok=True);t=p.with_suffix('.tmp');t.write_text(json.dumps(x,ensure_ascii=False,indent=2)+'\n');t.replace(p)
def sha(p):
 h=hashlib.sha256()
 with p.open('rb') as f:
  for b in iter(lambda:f.read(8*1024*1024),b''):h.update(b)
 return h.hexdigest()
def state(u):return subprocess.run(['systemctl','is-active',u],capture_output=True,text=True).stdout.strip()
def engines():
 rows=[]
 for p in P('/proc').iterdir():
  if not p.name.isdigit():continue
  try:a=[x.decode() for x in (p/'cmdline').read_bytes().split(b'\0') if x]
  except (OSError,UnicodeError):continue
  if not a:continue
  n=P(a[0]).name
  if n in ['gufo','strata','flash_serve','halogen','halogen-server','hipfire','vllm','llama-server','ollama','ninfer-serve'] or any(x in ['serve.server','vllm.entrypoints.openai.api_server','sglang.launch_server'] for x in a[1:]):
   rows.append({'pid':int(p.name),'name':n,'registered':a[0]==str(SOURCE/'engine/strata') or 'serve.server' in a and any(str(R/'configs') in x for x in a)})
 return rows
def available():return next(int(x.split()[1])*1024 for x in P('/proc/meminfo').read_text().splitlines() if x.startswith('MemAvailable:'))
def current():return read(R/'current.json')['profile']
def config(p):return read(R/'configs'/(p+'.json'))
def digest(c):return hashlib.sha256(json.dumps({k:v for k,v in c.items() if k!='api_key'},sort_keys=True).encode()).hexdigest()
def api(path):
 c=config(current());req=urllib.request.Request('http://127.0.0.1:'+str(PORT)+path,headers={'Authorization':'Bearer '+c['api_key']})
 with urllib.request.urlopen(req,timeout=10) as f:return json.load(f)
def alive(pid):
 try:return P('/proc/'+str(pid)+'/stat').read_text().split()[2]!='Z'
 except FileNotFoundError:return False
def quiet():
 for p in (R/'jobs').glob('*.json'):
  d=read(p);assert d.get('status')!='running' or not alive(d['pid']),'previous case active'
def guard():
 profile=current();c=config(profile);e=engines();assert len(e)==2 and all(x['registered'] for x in e),e
 assert all(state(u) not in ['active','activating','reloading'] for u in [*PROD,'ai-llm-halogen.service','ai-gsq-unsloth-eval-20261015.service'])
 status=api('/v1/status');assert status['loaded'] and status['activity']['in_flight']==0
 assert available()>=12*2**30,'available RAM below 12 GiB'
 seal=read(R/'seals'/(profile+'.json'));assert digest(c)==seal['config_without_key_sha256']
 for f in seal['asset_files']:
  st=P(f['path']).stat();assert st.st_size==f['bytes'] and st.st_mtime_ns==f['mtime_ns'],'sealed asset changed'
 assert status['model']==c['model_name']
 sys.path.insert(0,str(S));from resource_probe import snapshot
 return {'profile':profile,'epoch':time.time(),'boot_id':P('/proc/sys/kernel/random/boot_id').read_text().strip(),'processes':e,'resource':snapshot(),'config_without_key_sha256':digest(c),'activity':status['activity']}
def stop():
 quiet();subprocess.run(['sudo','-n','systemctl','stop',UNIT],check=True)
 end=time.monotonic()+75
 while engines() and time.monotonic()<end:time.sleep(1)
 assert not engines(),engines();assert available()>=100*2**30
 return {'stopped':True,'MemAvailable':available()}
def configure():
 assert not (R/'configs').exists(),'preserve configuration'
 original=read(OLD/'configs/unsloth-iq4xs.json');seal=read(OLD/'seals/unsloth-iq4xs.json')
 for f in seal['asset_files']:
  st=P(f['path']).stat();assert st.st_size==f['bytes'] and st.st_mtime_ns==f['mtime_ns'],'previously SHA-verified asset changed'
 binary=P(original['exe']);expected=next(x['sha256'] for x in seal['asset_files'] if x['path']==str(binary));assert sha(binary)==expected
 key=secrets.token_hex(32);(R/'api-key').write_text(key);(R/'api-key').chmod(0o600)
 for profile,settings in PROFILES.items():
  c=json.loads(json.dumps(original));args=c['args'];args[args.index('--expert-cache')+1]=str(settings['expert_cache_units']);args[args.index('--prefill')+1]=settings['prefill'];args+=settings['extra_args'];c['env'].update(settings['env'])
  c.update(api_key=key,port=PORT,model_name='Qwen3.8-Next-Flash-tune-'+profile,reasoning_effort=settings['reasoning_effort'],log=str(R/(profile+'-engine.log')))
  save(R/'configs'/(profile+'.json'),c);(R/'configs'/(profile+'.json')).chmod(0o600)
  save(R/'seals'/(profile+'.json'),{'profile':profile,'epoch':time.time(),'config_without_key_sha256':digest(c),'config':{k:v for k,v in c.items() if k!='api_key'},'asset_files':seal['asset_files'],'asset_verification':'prior full SHA plus current size/mtime; engine full SHA rechecked','previous_seal_sha256':sha(OLD/'seals/unsloth-iq4xs.json'),'engine_build':read(SOURCE/'engine/BUILD.json')})
 return {'configured':list(PROFILES),'assets':len(seal['asset_files']),'engine_sha256':expected}
def action(a):
 if a[0]=='configure':return configure()
 if a[0]=='isolate':
  assert not (R/'production-paused.json').exists();quiet();assert all(x['name']=='gufo' for x in engines())
  for port in [8000,8001,8735]:assert not subprocess.run(['ss','-Htn','state','established','( sport = :'+str(port)+' or dport = :'+str(port)+' )'],capture_output=True,text=True,check=True).stdout.strip(),'active client'
  d={'epoch':time.time(),'original':{u:state(u) for u in PROD}}
  for u in PROD:subprocess.run(['sudo','-n','systemctl','stop',u],check=True)
  end=time.monotonic()+75
  while engines() and time.monotonic()<end:time.sleep(1)
  assert not engines();assert available()>=100*2**30;d['MemAvailable']=available();save(R/'production-paused.json',d);return d
 if a[0]=='start':
  quiet();profile=a[1];assert profile in PROFILES;assert not engines();assert available()>=100*2**30;assert all(state(u)!='active' for u in PROD)
  c=config(profile);save(R/'current.json',{'profile':profile,'epoch':time.time()});started=time.time();user=subprocess.check_output(['id','-un'],text=True).strip()
  cmd=['sudo','-n','systemd-run','--unit='+UNIT,'--collect','--property=User='+user,'--property=WorkingDirectory='+str(SOURCE),'--property=MemoryMax=116G','--property=MemorySwapMax=0','--property=LimitMEMLOCK=infinity',str(SOURCE/'.venv/bin/python'),'-m','serve.server','--engine','strata','--config',str(R/'configs'/(profile+'.json')),'--host','127.0.0.1','--port',str(PORT)]
  subprocess.run(cmd,check=True);d={'profile':profile,'start_requested_epoch':started,'free_memory_before':available()};save(R/'startups'/(str(time.time_ns())+'.json'),d);return d
 if a[0]=='stop':return stop()
 if a[0]=='guard':return guard()
 if a[0]=='status':
  out={'unit':state(UNIT),'processes':engines(),'MemAvailable':available()}
  try:out['status']={k:v for k,v in api('/v1/status').items() if k in ['model','loaded','activity','context','last_timings']}
  except Exception as e:out['status_error']=type(e).__name__
  return out
 if a[0]=='case':
  quiet();phase,kind,task,rnd=a[1:5];rnd=int(rnd);profile=current();assert rnd in [1,2]
  assert phase in ['screen','calibrate','validate','warmup']
  if phase=='screen':assert kind=='speed' and task in ['prompt4k','prompt32k'] and profile.endswith('-medium')
  elif phase=='calibrate':assert kind=='short' and task in ['C03','A02','W03']
  elif phase=='warmup':assert kind=='short' and task=='D01'
  else:assert kind=='long' and task=='LH01' or kind=='short' and task in ['D01','C01','W01','A01','C03','A02','W03']
  guard();label='-'.join([phase,profile,kind,task,'r'+str(rnd)]);j=R/'jobs'/(label+'.json');assert not j.exists(),'preserve original attempt'
  c=config(profile);env={**os.environ,'EVAL_PROFILE':profile,'EVAL_MODEL':'Qwen/Qwen3.8-Flash-Next','EVAL_BASE_URL':'http://127.0.0.1:'+str(PORT)+'/v1','EVAL_API_KEY':c['api_key'],'EVAL_SEED':str(2026101600+rnd),'EVAL_GUARD_COMMAND':json.dumps(['python3',str(R/'study/runtime_controller.py'),'guard']),'PYTHONUTF8':'1'}
  output=R/'results'/phase/kind
  if kind=='short':cmd=['python3',str(S/'short_runner.py'),'--provider','local','--task',task,'--round',str(rnd),'--output',str(output/profile)]
  elif kind=='long':cmd=['python3',str(S/'long-horizon/runner.py'),'--provider','local','--profile',profile,'--round',str(rnd),'--output',str(output)]
  else:cmd=['python3',str(S/'speed_runner.py'),'--profile',profile,'--kind',task,'--round',str(rnd),'--output',str(output)]
  j.parent.mkdir(exist_ok=True)
  with j.with_suffix('.log').open('w') as f:p=subprocess.Popen(['python3',str(S/'runtime_controller.py'),'worker',label,json.dumps(cmd)],env=env,stdout=f,stderr=f,start_new_session=True)
  d={'label':label,'profile':profile,'phase':phase,'kind':kind,'task':task,'round':rnd,'pid':p.pid,'status':'running','start':time.time()};save(j,d);return d
 if a[0]=='worker':
  label=a[1];j=R/'jobs'/(label+'.json');time.sleep(.3);d=read(j)
  try:d['returncode']=subprocess.run(json.loads(a[2]),timeout=2500 if d['kind']=='long' else 630).returncode;d['status']='finished' if d['returncode']==0 else 'failed'
  except Exception as e:d.update(status='failed',error=type(e).__name__+': '+str(e))
  d['finish']=time.time();save(j,d);return {'status':d['status']}
 if a[0]=='job':
  j=R/'jobs'/(a[1]+'.json');end=time.monotonic()+min(40,int(a[2]) if len(a)>2 else 0)
  while read(j)['status']=='running' and time.monotonic()<end:time.sleep(1)
  return {'job':read(j),'tail':j.with_suffix('.log').read_text()[-5000:]}
 if a[0]=='restore':
  if engines():stop()
  d=read(R/'production-paused.json')
  for u,v in reversed(list(d['original'].items())):
   if v=='active':subprocess.run(['sudo','-n','systemctl','start',u],check=True)
  out={'epoch':time.time(),'services':{u:state(u) for u in PROD}};save(R/'production-restored.json',out);return out
 raise ValueError(a[0])
if __name__=='__main__':
 try:print(json.dumps(action(sys.argv[1:]),ensure_ascii=False))
 except Exception as e:print(json.dumps({'error':type(e).__name__+': '+str(e)},ensure_ascii=False));raise SystemExit(1)
