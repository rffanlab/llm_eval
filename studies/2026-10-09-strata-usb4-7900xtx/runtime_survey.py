"""Read-only Linux hardware/memory snapshot; no environment or credentials."""
import argparse,datetime,json,os,platform,subprocess
from pathlib import Path
p=argparse.ArgumentParser();p.add_argument('--profile',required=True);a=p.parse_args()
def text(path):
    try:return Path(path).read_text().strip()
    except OSError:return None
mem={k:int(v.split()[0])*1024 for k,v in (l.split(':',1) for l in Path('/proc/meminfo').read_text().splitlines()) if v.strip().split()[-1]=='kB'}
gpu={}
for root in Path('/sys/bus/pci/devices').iterdir():
    if text(root/'vendor')!='0x1002' or not (root/'mem_info_vram_total').exists():continue
    pci=root.name
    gpu[pci]={k:text(root/k) for k in ['vendor','device','mem_info_vram_total','mem_info_vram_used','mem_info_gtt_total','mem_info_gtt_used','gpu_busy_percent','current_link_speed','current_link_width','max_link_speed','max_link_width']}
xtx=Path('/sys/bus/pci/devices/0000:05:00.0').resolve()
chain=[]
for root in [xtx,*xtx.parents]:
    if (root/'current_link_speed').exists():chain.append({'pci':root.name,'speed':text(root/'current_link_speed'),'width':text(root/'current_link_width')})
processes=[]
for root in Path('/proc').iterdir():
    if not root.name.isdigit():continue
    try:
        name=(root/'comm').read_text().strip()
        if name not in ['strata','halogen','python3','aria2c','cc1plus','sha256sum']:continue
        st=dict(l.split(':',1) for l in (root/'status').read_text().splitlines())
        processes.append({'pid':int(root.name),'name':name,'state':st['State'].strip(),'rss':st.get('VmRSS','').strip(),'swap':st.get('VmSwap','').strip()})
    except OSError:pass
r={'profile':a.profile,'captured_at':datetime.datetime.now(datetime.timezone.utc).isoformat(),'cpu':'Ryzen AI Max+395','ram_installed_gb':128,'external_gpu':'RX7900XTX 24GB via USB4','kernel':platform.release(),'os_release':text('/etc/os-release'),'meminfo_bytes':mem,'gpu_sysfs':gpu,'xtx_upstream_link_chain':chain,'processes':processes,'hip_compiler':subprocess.check_output(['/opt/rocm/bin/hipcc','--version'],text=True),'rocm_version':text('/opt/rocm/.info/version')}
print(json.dumps(r,ensure_ascii=False,indent=2))
