"""Two-second local samples; source PID identity, ECC, page faults and SSD I/O retained."""
from pathlib import Path
import json
import os
import sys
import time


def snapshot():
    if sys.platform=='win32':return {'epoch':time.time(),'not_execution_host':True}
    row={'epoch':time.time(),'boot_id':Path('/proc/sys/kernel/random/boot_id').read_text().strip(),
         'memory':Path('/proc/meminfo').read_text(),'loadavg':os.getloadavg(),
         'EDAC':{str(p):p.read_text().strip() for p in Path('/sys/devices/system/edac/mc').glob('mc*/[cu]e_count')},
         'GPU':{str(p):p.read_text().strip() for pattern in ['card[0-9]/device/mem_info_vram_used','card[0-9]/device/mem_info_gtt_used','card[0-9]/device/power/control','card[0-9]/device/hwmon/hwmon*/power1_cap'] for p in Path('/sys/class/drm').glob(pattern)},
         'diskstats':[line for line in Path('/proc/diskstats').read_text().splitlines() if 'nvme0n1' in line],
         'vmstat':{k:int(v) for line in Path('/proc/vmstat').read_text().splitlines() for k,v in [line.split()] if k.startswith(('pgfault','pgmajfault','pgpgin','pgpgout','pgscan','pgsteal','pgmigrate','pswp'))},
         'process_identity_known':False}
    pid=os.environ.get('EVAL_ENGINE_PID');exe=os.environ.get('EVAL_ENGINE_EXE')
    if pid and exe:
        p=Path('/proc')/pid
        try:
            args=(p/'cmdline').read_bytes().decode(errors='replace').split('\0')
            row['process']={'PID':int(pid),'argv':args,'stat':(p/'stat').read_text(),
                            'status':(p/'status').read_text(),'io':(p/'io').read_text()}
            row['process_identity_known']=bool(args and args[0]==exe)
        except FileNotFoundError:row['process_exited']=True
    return row


def sampler(stop,path):
    if sys.platform=='win32':return
    with path.open('x',encoding='utf-8') as out:
        while not stop.is_set():
            try:row=snapshot()
            except Exception as exc:row={'epoch':time.time(),'sample_error':{'type':type(exc).__name__,'text':str(exc)}}
            out.write(json.dumps(row,ensure_ascii=False)+'\n');out.flush();stop.wait(2)
