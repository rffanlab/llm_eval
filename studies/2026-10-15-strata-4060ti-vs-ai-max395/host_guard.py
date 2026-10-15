"""Private, host-local lifecycle and per-call resource admission. Never prints keys."""
import sys,os,json,pathlib,subprocess,time,hashlib,urllib.request,pwd
R=pathlib.Path('/srv/ai/services/strata-eval-20261015');SOURCE=R/'source';PROFILE=json.loads((R/'private-profile.json').read_text())['profile'];UNIT='ai-strata-eval-20261015.service';CONFIG=R/'measured-private.json'
def save(p,x):p.write_text(json.dumps(x,ensure_ascii=False,indent=2)+'\n')
def state(u):return subprocess.run(['systemctl','is-active',u],capture_output=True,text=True).stdout.strip()
def engines():
 out=[]
 for p in pathlib.Path('/proc').iterdir():
  if not p.name.isdigit():continue
  try:a=[x.decode() for x in (p/'cmdline').read_bytes().split(b'\0') if x]
  except (OSError,UnicodeError):continue
  if not a:continue
  name=pathlib.Path(a[0]).name
  if name in ['gufo','strata','flash_serve','llama-server','ollama','vllm'] or any(x in ['serve.server','vllm.entrypoints.openai.api_server','sglang.launch_server'] for x in a[1:]):
   own=name=='strata' and a[0]==str(SOURCE/'engine/strata') or 'serve.server' in a and str(CONFIG) in a
   out.append({'pid':int(p.name),'name':name,'registered':own})
 return out
def available():return next(int(x.split()[1])*1024 for x in pathlib.Path('/proc/meminfo').read_text().splitlines() if x.startswith('MemAvailable:'))
def status():
 c=json.loads(CONFIG.read_text());req=urllib.request.Request('http://127.0.0.1:8744/v1/status',headers={'Authorization':'Bearer '+c['api_key']})
 with urllib.request.urlopen(req,timeout=10) as f:return json.load(f)
def guard():
 d=status();p=engines();assert len(p)==2 and all(x['registered'] for x in p),p
 assert d['loaded'] and d['activity']['in_flight']==0,d['activity']
 avail=available();assert avail>=8*1024**3,('insufficient memory headroom',avail)
 c=json.loads(CONFIG.read_text());c.pop('api_key',None);digest=hashlib.sha256(json.dumps(c,sort_keys=True).encode()).hexdigest()
 if (R/'sealed-identity.json').exists():assert digest==json.loads((R/'sealed-identity.json').read_text())['config_without_key_sha256'],'configuration changed after identity seal'
 return {'profile':PROFILE,'checked_at_epoch':time.time(),'processes':p,'MemAvailable_bytes':avail,'admission_headroom_bytes':8*1024**3,'boot_id':pathlib.Path('/proc/sys/kernel/random/boot_id').read_text().strip(),'loaded':True,'activity':d['activity'],'config_without_key_sha256':digest}

if __name__=='__main__':print(json.dumps(guard()))
