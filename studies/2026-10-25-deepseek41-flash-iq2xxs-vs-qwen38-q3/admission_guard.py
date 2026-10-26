"""Read-only per-call admission against a private, previously approved deployment binding."""
from pathlib import Path
import argparse
import hashlib
import json
import os
import subprocess
import time


def hardware_history(binding):
    # Read the RAS database and retired-page flags with the already authorized
    # root boundary. EDAC zero alone did not expose the observed corrected MCE.
    source="""import json,sqlite3,struct,subprocess
from pathlib import Path
b=json.loads(__import__('sys').argv[1])
c=sqlite3.connect('file:/var/lib/rasdaemon/ras-mc_event.db?mode=ro',uri=True)
r={t:list(c.execute('select max(id),count(*) from '+t).fetchone()) for t in ['mc_event','mce_record','aer_event']}
c.close()
with open('/proc/kpageflags','rb') as f:
 f.seek(int(b['corrected_page_pfn'],16)*8);flags=struct.unpack('<Q',f.read(8))[0]
k=subprocess.run(['journalctl','-k','-b','--since','@'+str(b['kernel_checkpoint_epoch']),'--no-pager','-o','short-iso'],capture_output=True,text=True,timeout=15)
assert k.returncode==0,k.stderr
print(json.dumps({'RAS_max_ids':r,'retired_page_flags':hex(flags),'HWPOISON_bit19':bool(flags&(1<<19)),'kernel_since_checkpoint':k.stdout}))
"""
    p=subprocess.run(['sudo','-n','python3','-B','-c',source,json.dumps(binding)],capture_output=True,text=True,timeout=20)
    assert p.returncode==0,('Cannot verify kernel/RAS/page retirement',p.stderr)
    result=json.loads(p.stdout)
    assert result['RAS_max_ids']==binding['RAS_baseline_max_ids'],('RAS event history changed',result)
    assert result['HWPOISON_bit19'],'Known corrected page retirement no longer matches'
    return result


def inspect(binding):
    now=time.time();boot=Path('/proc/sys/kernel/random/boot_id').read_text().strip()
    assert boot==binding['boot_id'],'Boot changed; retain diagnostics before continuing'
    pid=int(binding['engine_PID']);p=Path('/proc')/str(pid)
    raw=(p/'cmdline').read_bytes()
    assert hashlib.sha256(raw).hexdigest()==binding['engine_cmdline_SHA256'],'Engine PID/argv identity changed'
    assert int((p/'stat').read_text().rsplit(') ',1)[1].split()[19])==binding['engine_start_ticks'],'Engine PID instance changed'
    assert Path(raw.split(b'\0')[0].decode()).resolve()==Path(binding['engine_exe']).resolve()
    memory=Path('/proc/meminfo').read_text()
    def kb(name):return int(next(l.split()[1] for l in memory.splitlines() if l.startswith(name+':')))
    assert kb('MemAvailable')>=8*2**20,'Available RAM below the registered8GiB admission floor'
    assert kb('HardwareCorrupted')==binding['known_HardwareCorrupted_kB'],'Retired-page total changed'
    edac={str(p):p.read_text().strip() for p in Path('/sys/devices/system/edac/mc').glob('mc*/[cu]e_count')}
    assert edac and edac==binding['EDAC_controller_baseline'],'EDAC counters changed'
    gpu={str(p):p.read_text().strip() for pattern in ['card[0-9]/device/mem_info_vram_used','card[0-9]/device/mem_info_gtt_used','card[0-9]/device/power/control','card[0-9]/device/hwmon/hwmon*/power1_cap'] for p in Path('/sys/class/drm').glob(pattern)}
    assert [v for k,v in gpu.items() if k.endswith('/power1_cap')]==['265000000'],'Power cap changed'
    assert [v for k,v in gpu.items() if k.endswith('/power/control')]==['auto'],'GPU power/control changed'
    proc={};models=[];transfers=[]
    for q in Path('/proc').iterdir():
        if not q.name.isdigit():continue
        try:
            args=(q/'cmdline').read_bytes().decode(errors='replace').split('\0')
            parent=int((q/'stat').read_text().rsplit(') ',1)[1].split()[1]);proc[int(q.name)]=(parent,args)
        except FileNotFoundError:continue
    for qpid,(parent,args) in proc.items():
        name=Path(args[0]).name.lower() if args and args[0] else ''
        if name in ('rsync','scp','sftp') or any('archive_worker' in arg for arg in args):transfers.append({'PID':qpid,'argv':args})
        is_model=name in ('strata','strata-dsv41','llama-server') or name.startswith(('halogen','gufo')) or 'serve.server' in args
        if not is_model:continue
        ancestor=qpid;seen=set()
        while ancestor in proc and ancestor not in seen and ancestor!=binding['server_PID']:
            seen.add(ancestor);ancestor=proc[ancestor][0]
        assert ancestor==binding['server_PID'],('Another model process',qpid,args)
        models.append({'PID':qpid,'argv':args})
    assert len([x for x in models if x['PID']!=binding['server_PID']])==1,'Expected exactly one main inference engine'
    assert not transfers,('Bulk transfer/archive I/O active',transfers)
    paths=[]
    for x in binding['immutable_weight_bindings']:
        q=Path(x['path']);s=q.stat()
        assert q.resolve()==q and not q.is_symlink(),'Working weights must be real SSD files'
        assert (s.st_size,s.st_mtime_ns,s.st_ino)==(x['bytes'],x['mtime_ns'],x['inode']),('Weight binding changed',x['path'])
        paths.append(x['path'])
    mount=json.loads(subprocess.check_output(['findmnt','--json','-T',binding['run_root'],'-o','SOURCE,FSTYPE,UUID'],text=True))['filesystems'][0]
    assert mount=={'source':'/dev/nvme0n1p2','fstype':'ext4','uuid':'4aff05eb-6d27-44bf-87f7-ea07dd7960b7'}
    for x in binding['immutable_weight_bindings']:
        assert Path(x['path']).stat().st_dev==binding['SSD_device_number'],'Weight is on a different device'
    hardware=hardware_history(binding)
    critical=[line for line in hardware['kernel_since_checkpoint'].splitlines() if any(k in line.lower() for k in ['hardware error','machine check','soft-offlining','uncorrected']) or ('amdgpu' in line.lower() and any(k in line.lower() for k in ['gpu reset','gpu fault','ring timeout']))]
    assert not critical,('New hardware event after the reviewed checkpoint',critical)
    return {'epoch':now,'boot_id':boot,'engine_PID':pid,'engine_cmdline_SHA256':binding['engine_cmdline_SHA256'],
            'model_processes':models,'memory':memory,'EDAC_controller_counts':edac,'GPU':gpu,'SSD_mount':mount,
            'immutable_weight_bindings_match':len(paths),'SSD_free_bytes':os.statvfs(binding['run_root']).f_bavail*os.statvfs(binding['run_root']).f_frsize,
            'hardware_history':hardware,'known_corrected_history':binding['known_corrected_history'],
            'retired_page_total_kB':kb('HardwareCorrupted'),'new_hardware_event_since_checkpoint':False}


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--binding',type=Path,required=True)
    args=parser.parse_args();print(json.dumps(inspect(json.loads(args.binding.read_text())),ensure_ascii=False))
