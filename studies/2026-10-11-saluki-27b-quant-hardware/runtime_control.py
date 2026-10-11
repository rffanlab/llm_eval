import hashlib,json,os,pathlib,secrets,subprocess,sys,time,urllib.request
HOST='rtx3090' if pathlib.Path('/srv/e5-data/saluki-eval-20261011').exists() else 'ai-max395'
ROOT=pathlib.Path('/srv/e5-data/saluki-eval-20261011' if HOST=='rtx3090' else '/srv/ai/services/saluki-eval-20261011')
MROOT=pathlib.Path('/srv/e5-models/saluki-20261011' if HOST=='rtx3090' else '/srv/ai/models/llm/saluki-20261011')
UNIT='saluki-eval-20261011.service';BIN=ROOT/'build/bin/llama-server';PORT=18093
GPU_UUID='GPU-d93110c9-3b8a-7db7-b9f5-f510c5c45527'
PROD=['e5-ninfer-api.service','e5-ninfer-3090.service'] if HOST=='rtx3090' else ['ai-llm-router.service','ai-llm-gufo.service']
def state(unit):return subprocess.run(['systemctl','is-active',unit],capture_output=True,text=True).stdout.strip()
def call(path):
 req=urllib.request.Request('http://127.0.0.1:'+str(PORT)+path,headers={'Authorization':'Bearer '+(ROOT/'api-key').read_text().strip()})
 with urllib.request.urlopen(req,timeout=6) as r:return json.load(r)
def memory():return next(int(l.split()[1])*1024 for l in pathlib.Path('/proc/meminfo').read_text().splitlines() if l.startswith('MemAvailable:'))
def processes():
 rows=[]
 for p in pathlib.Path('/proc').iterdir():
  if not p.name.isdigit():continue
  try:a=[x.decode() for x in (p/'cmdline').read_bytes().split(b'\0') if x]
  except (OSError,UnicodeError):continue
  if not a:continue
  name=pathlib.Path(a[0]).name
  if name in ['ninfer-serve','llama-server','gufo','strata','flash_serve','ollama','hipfire'] or (name.startswith('python') and any(x in ['sglang.launch_server','vllm.entrypoints.openai.api_server','serve.server'] for x in a[1:])):
   rows.append({'pid':int(p.name),'executable':name,'owned':a[0]==str(BIN),'model_files':[pathlib.Path(x).name for x in a if x.endswith(('.gguf','.ninfer'))]})
 return rows
def gpu():
 if HOST=='rtx3090':
  raw=subprocess.check_output(['nvidia-smi','--id='+GPU_UUID,'--query-gpu=memory.total,memory.used,utilization.gpu,temperature.gpu,power.draw','--format=csv,noheader,nounits'],text=True).strip().split(',')
  return [{'total_bytes':int(raw[0])*2**20,'used_bytes':int(raw[1])*2**20,'utilization_percent':int(raw[2]),'temperature_c':int(raw[3]),'power_w':float(raw[4])}]
 result=[]
 for p in pathlib.Path('/sys/class/drm').glob('card*/device'):
  if '-' in p.parent.name or not (p/'vendor').exists() or (p/'vendor').read_text().strip()!='0x1002':continue
  row={'pci':p.resolve().name,'VRAM':int((p/'mem_info_vram_used').read_text()),'GTT':int((p/'mem_info_gtt_used').read_text())}
  if (p/'gpu_busy_percent').exists():row['gpu_busy_percent']=int((p/'gpu_busy_percent').read_text())
  row['hwmon']={}
  for mon in (p/'hwmon').glob('hwmon*'):
   for name in ['temp1_input','temp2_input','temp3_input','power1_average','power1_input']:
    if (mon/name).exists():row['hwmon'][name]=int((mon/name).read_text())
  result.append(row)
 return result
def snapshot():return {'epoch':time.time(),'boot_id':pathlib.Path('/proc/sys/kernel/random/boot_id').read_text().strip(),'MemAvailable_bytes':memory(),'gpu':gpu(),'processes':processes(),'loadavg':pathlib.Path('/proc/loadavg').read_text().strip()}
def connections(port):
 p=subprocess.run(['ss','-Htn','state','established','( sport = :'+str(port)+' or dport = :'+str(port)+' )'],capture_output=True,text=True,check=True)
 return len(p.stdout.splitlines())
def released():
 stop=time.monotonic()+180
 while time.monotonic()<stop:
  d=snapshot();g=d['gpu']
  safe=(d['MemAvailable_bytes']>=40*2**30 and g[0]['used_bytes']<2**30) if HOST=='rtx3090' else (d['MemAvailable_bytes']>=100*2**30 and len(g)==1 and g[0]['GTT']<4*2**30 and g[0]['VRAM']<2*2**30)
  if not d['processes'] and safe:return d
  time.sleep(2)
 raise RuntimeError('previous model allocations not released')
def guard(profile):
 d=snapshot();rows=d['processes'];assert len(rows)==1 and rows[0]['owned'],'another inference engine detected'
 assert d['MemAvailable_bytes']>=8*2**30,'RAM admission failed'
 if HOST=='rtx3090':assert d['gpu'][0]['total_bytes']-d['gpu'][0]['used_bytes']>=512*2**20,'VRAM admission failed'
 else:
  assert len(d['gpu'])==1 and d['gpu'][0]['pci']=='0000:c5:00.0','AMD device enumeration changed'
  assert d['gpu'][0]['GTT']+d['gpu'][0]['VRAM']<=24*2**30,'24GiB allocation limit exceeded'
 assert all(state(u) not in ['active','activating','reloading'] for u in PROD)
 assert state(UNIT)=='active';assert json.loads((ROOT/'active-profile.json').read_text())['profile']==profile
 models=call('/v1/models');assert models['data'][0]['id']==HOST+'-'+profile
 assert all(not x.get('is_processing',False) for x in call('/slots')),'slot busy'
 d['profile']=HOST+'-'+profile;return d
def save(name,d):
 p=ROOT/name;assert not p.exists(),'preserve lifecycle attempt';p.write_text(json.dumps(d,indent=2)+'\n')
def stop():
 subprocess.run(['sudo','-n','systemctl','stop',UNIT],check=True)
 return released()
def action(args):
 which=args[0]
 if which=='snapshot':return snapshot()
 if which=='guard':return guard(args[1])
 if which=='released':return released()
 if which=='pause':
  original={u:state(u) for u in PROD};assert all(v=='active' for v in original.values()),'unexpected original service state'
  production_port=18081 if HOST=='rtx3090' else 8735
  assert connections(production_port)==0,'production request or connection present'
  for u in PROD:subprocess.run(['sudo','-n','systemctl','stop',u],check=True)
  d={'original':original,'released':released()};save('production-paused.json',d);return d
 if which=='launch':
  profile=args[1];before=released();models=json.loads((ROOT/'models.json').read_text());m=next(x for x in models if x['id']==profile)
  path=MROOT/m['filename'] if profile!='qwen-q4' or HOST=='rtx3090' else pathlib.Path('/srv/ai/models/llm/gufo-qwen27b-20261010')/m['filename']
  verified=json.loads((ROOT/'weights-verified.json').read_text());assert any(x['sha256']==m['sha256'] and x['bytes']==m['bytes'] for x in verified)
  started=time.time();mono=time.monotonic();save(profile+'-launch-start.json',{'profile':profile,'epoch':started,'before':before})
  (ROOT/'active-profile.json').write_text(json.dumps({'profile':profile,'epoch':started}))
  flags=[str(BIN),'--model',str(path),'--host','127.0.0.1','--port',str(PORT),'--alias',HOST+'-'+profile,'--api-key-file',str(ROOT/'api-key'),'--ctx-size','32768','--parallel','1','--batch-size','512','--ubatch-size','256','--threads','8','--threads-batch','16','--gpu-layers','all','--split-mode','none','--main-gpu','0','--fit','off','--flash-attn','on','--cache-type-k','f16','--cache-type-v','f16','--jinja','--chat-template-file',str(ROOT/'chat-template.jinja'),'--reasoning-format','deepseek','--reasoning-budget','-1','--no-reasoning-preserve','--spec-type','none','--perf','--no-context-shift','--offline','--no-webui','--metrics']
  flags+=['--verbosity','4']
  if HOST=='rtx3090':
   flags=['docker','run','--rm','--name','saluki-eval-model','--network','host','--gpus','device='+GPU_UUID,'-e','CUDA_VISIBLE_DEVICES=0','-e','TMPDIR='+str(ROOT/'cache'),'-v',str(ROOT)+':'+str(ROOT),'-v',str(MROOT)+':'+str(MROOT)+':ro','nvcr.io/nvidia/cuda:12.8.1-devel-ubuntu24.04']+flags
  command=['sudo','-n','systemd-run','--collect','--unit='+UNIT.removesuffix('.service'),'--service-type=exec','--property=WorkingDirectory='+str(ROOT),'--setenv=TMPDIR='+str(ROOT/'cache')]
  if HOST=='ai-max395':command+=['--property=User=rffan','--setenv=ROCR_VISIBLE_DEVICES=0','--setenv=HIP_VISIBLE_DEVICES=0','--setenv=GPU_MAX_ALLOC_PERCENT=100','--setenv=GPU_SINGLE_ALLOC_PERCENT=100']
  subprocess.run(command+flags,check=True,stdout=subprocess.DEVNULL)
  deadline=time.monotonic()+600
  while time.monotonic()<deadline:
   if state(UNIT) in ['failed','inactive','unknown']:
    d={'profile':profile,'load_s':time.monotonic()-mono,'status':'failed_before_ready'};save(profile+'-launch-result.json',d);return d
   current_gpu=gpu()
   over_limit=(current_gpu[0]['GTT']+current_gpu[0]['VRAM']>24*2**30) if HOST=='ai-max395' else (current_gpu[0]['total_bytes']-current_gpu[0]['used_bytes']<512*2**20)
   if over_limit:
    subprocess.run(['sudo','-n','systemctl','stop',UNIT],check=True)
    d={'profile':profile,'load_s':time.monotonic()-mono,'status':'skipped_resource_limit','gpu':current_gpu,'released':released()};save(profile+'-launch-result.json',d);return d
   try:d=guard(profile);break
   except (AssertionError,urllib.error.URLError):time.sleep(2)
  else:raise RuntimeError('readiness timeout')
  text=subprocess.check_output(['sudo','-n','journalctl','-u',UNIT,'--since','@'+str(int(started)),'--no-pager','-o','cat'],text=True)
  import re
  matches=re.findall(r'offloaded (\d+)/(\d+) layers to GPU',text)
  if not matches or any(x!=y for x,y in matches):raise RuntimeError('full GPU offload not verified')
  result={'profile':profile,'status':'ready','load_and_ready_s':time.monotonic()-mono,'filesystem_cache_controlled':False,'offloaded_layers':matches[-1],'state':d};save(profile+'-launch-result.json',result);return result
 if which=='stop':
  profile=args[1];d=stop();save(profile+'-released.json',d)
  start=json.loads((ROOT/(profile+'-launch-start.json')).read_text())['epoch']
  text=subprocess.check_output(['sudo','-n','journalctl','-u',UNIT,'--since','@'+str(int(start)),'--no-pager','-o','short-iso'],text=True)
  text=text.replace((ROOT/'api-key').read_text().strip(),'[REDACTED]');(ROOT/(profile+'-journal.txt')).write_text(text)
  return d
 if which=='restore':
  if state(UNIT)=='active':stop()
  released()
  for u in reversed(PROD):subprocess.run(['sudo','-n','systemctl','start',u],check=True)
  d=snapshot();d['services']={u:state(u) for u in PROD};save('production-restored.json',d);return d
 if which=='sample':
  target=ROOT/(args[1]+'-resources.jsonl');assert not target.exists()
  with target.open('a') as out:
   while True:
    d=snapshot();out.write(json.dumps(d)+'\n');out.flush()
    if HOST=='ai-max395' and any(x['owned'] for x in d['processes']) and any(x['GTT']+x['VRAM']>24*2**30 for x in d['gpu']):
     save(args[1]+'-resource-limit.json',{'status':'stopped_resource_limit','limit_bytes':24*2**30,'state':d})
     subprocess.run(['sudo','-n','systemctl','stop',UNIT],check=True)
     break
    time.sleep(1)
 if which=='sample-start':
  profile=args[1];guard(profile);subprocess.run(['sudo','-n','systemd-run','--collect','--unit=saluki-sampler-'+profile,'--property=User='+('rffanlab' if HOST=='rtx3090' else 'rffan'),'/usr/bin/python3',str(ROOT/'remote-control.py'),'sample',profile],check=True);return {'sampler':profile}
 if which=='sample-stop':subprocess.run(['sudo','-n','systemctl','stop','saluki-sampler-'+args[1]+'.service'],check=True);return {'sampler_stopped':args[1]}
 raise ValueError(which)
if __name__=='__main__':print(json.dumps(action(sys.argv[1:])))
