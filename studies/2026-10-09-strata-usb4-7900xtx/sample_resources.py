"""Lightweight two-second Linux sampler; stop with SIGTERM, preserve samples."""
import argparse,json,time,signal
from pathlib import Path
p=argparse.ArgumentParser();p.add_argument('--output',type=Path,required=True);p.add_argument('--limit-s',type=float,default=1830);a=p.parse_args()
assert not a.output.exists(),'preserve measurement'
devices=[p for p in Path('/sys/bus/pci/devices').iterdir() if (p/'vendor').exists() and (p/'device').exists() and (p/'vendor').read_text().strip()=='0x1002' and (p/'device').read_text().strip()=='0x744c' and (p/'mem_info_vram_total').exists() and 23*2**30<int((p/'mem_info_vram_total').read_text())<25*2**30]
assert len(devices)==1,'require exactly one verified Navi31 device with 24GiB VRAM'
gpu=devices[0]
running=True
def stop(signum,frame):
    global running
    running=False
signal.signal(signal.SIGTERM,stop);signal.signal(signal.SIGINT,stop)
def number(p):
    try:return int(p.read_text().strip())
    except (OSError,ValueError):return None
a.output.parent.mkdir(parents=True,exist_ok=True)
started=time.monotonic()
with a.output.open('x') as out:
    while running and time.monotonic()-started<a.limit_s:
        mem={k:int(v.split()[0])*1024 for k,v in (l.split(':',1) for l in Path('/proc/meminfo').read_text().splitlines()) if v.strip().split()[-1]=='kB'}
        vm={k:int(v) for k,v in (l.split() for l in Path('/proc/vmstat').read_text().splitlines()) if k in ['pswpin','pswpout','pgmajfault']}
        rss=swap=0;process=[]
        for root in Path('/proc').iterdir():
            if not root.name.isdigit():continue
            try:
                if (root/'comm').read_text().strip()!='strata':continue
                st=dict(l.split(':',1) for l in (root/'status').read_text().splitlines())
                r=int(st.get('VmRSS','0 kB').split()[0])*1024;s=int(st.get('VmSwap','0 kB').split()[0])*1024
                rss+=r;swap+=s;process.append(int(root.name))
            except OSError:pass
        row={'wall_epoch':time.time(),'elapsed_s':time.monotonic()-started,'MemAvailable':mem.get('MemAvailable'),'Cached':mem.get('Cached'),'SwapUsed':mem.get('SwapTotal',0)-mem.get('SwapFree',0),'vmstat':vm,'strata_rss':rss,'strata_swap':swap,'pids':process,'xtx_vram_used':number(gpu/'mem_info_vram_used'),'xtx_gtt_used':number(gpu/'mem_info_gtt_used'),'xtx_busy_pct':number(gpu/'gpu_busy_percent')}
        row['xtx_pci']=gpu.name
        assert row['xtx_vram_used'] is not None and row['xtx_gtt_used'] is not None and row['xtx_busy_pct'] is not None,'GPU telemetry unavailable'
        out.write(json.dumps(row)+'\n');out.flush();time.sleep(2)
