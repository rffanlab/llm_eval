"""One serial family session. Load once; no questions before primary frozen release."""
from pathlib import Path
import hashlib
import json
import os
import signal
import socket
import subprocess
import sys
import threading
import time
import traceback
import urllib.request

from admission_guard import inspect, hardware_history
from resource_probe import snapshot
from transport import verify_freeze

HERE=Path(__file__).resolve().parent


def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def save(path,value):
    tmp=path.with_suffix(path.suffix+'.tmp')
    tmp.write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n',encoding='utf-8');tmp.replace(path)


def processes():
    rows={}
    for p in Path('/proc').iterdir():
        if not p.name.isdigit():continue
        try:rows[int(p.name)]=((p/'cmdline').read_bytes().decode(errors='replace').split('\0'),int((p/'stat').read_text().rsplit(') ',1)[1].split()[1]))
        except FileNotFoundError:pass
    return rows


def main(gate_path):
    gate=json.loads(gate_path.read_text());run=Path(gate['run_root'])
    assert gate['primary_load_only_review'] and gate['formal_calls_require_separate_frozen_release']
    assert 0<=time.time()-gate['epoch']<180
    assert sha(__file__)==gate['session_source_SHA256']
    assert not run.exists(),'Keep the prior attempt; never repeat a session'
    assert Path('/proc/sys/kernel/random/boot_id').read_text().strip()==gate['boot_id']
    before=snapshot();assert 'HardwareCorrupted:     4 kB' in before['memory'] or int(next(x.split()[1] for x in before['memory'].splitlines() if x.startswith('HardwareCorrupted:')))==4
    hardware=hardware_history(gate)
    assert not any(any(k in l.lower() for k in ['hardware error','machine check','soft-offlining','uncorrected']) for l in hardware['kernel_since_checkpoint'].splitlines())
    for pid,(args,parent) in processes().items():
        name=Path(args[0]).name.lower() if args and args[0] else ''
        assert not (name in ('strata','strata-dsv41','llama-server','rsync','scp','sftp') or name.startswith(('halogen','gufo')) or 'serve.server' in args or any('archive_worker' in a for a in args)),('Existing model or bulk I/O',pid,args)
    for x in gate['immutable_weight_bindings']:
        p=Path(x['path']);s=p.stat()
        assert p.resolve()==p and not p.is_symlink()
        assert (s.st_size,s.st_mtime_ns,s.st_ino,s.st_dev)==(x['bytes'],x['mtime_ns'],x['inode'],gate['SSD_device_number'])
    for x in gate['small_file_bindings']:assert sha(x['path'])==x['sha256'],x['path']
    assert sha(gate['config']['exe'])==gate['binary_SHA256']
    mount=json.loads(subprocess.check_output(['findmnt','--json','-T',str(run.parent),'-o','SOURCE,FSTYPE,UUID'],text=True))['filesystems'][0]
    assert mount=={'source':'/dev/nvme0n1p2','fstype':'ext4','uuid':'4aff05eb-6d27-44bf-87f7-ea07dd7960b7'}
    assert int(next(x.split()[1] for x in before['memory'].splitlines() if x.startswith('MemAvailable:')))>=8*2**20
    with socket.socket() as sock:sock.bind(('127.0.0.1',8748))
    run.mkdir()
    if gate.get('profile_copy'):
        p=gate['profile_copy'];assert sha(p['path'])==p['sha256']
        with (run/'expert-profile.bin').open('xb') as f:f.write(Path(p['path']).read_bytes())
    cfg=gate['config'];save(run/'config.json',cfg)
    profile=Path(gate['dynamic_profile_path'])
    with (run/'profile-before.bin').open('xb') as f:f.write(profile.read_bytes())
    env=dict(os.environ,PYTHONDONTWRITEBYTECODE='1',PYTHONUNBUFFERED='1')
    for k,rel in [('TMPDIR','runtime-tmp'),('TEMP','runtime-tmp'),('TMP','runtime-tmp'),('XDG_CACHE_HOME','runtime-cache'),('HF_HOME','runtime-cache/hf'),('TORCH_HOME','runtime-cache/torch'),('PIP_CACHE_DIR','runtime-cache/pip')]:env[k]=str(run.parent/rel)
    argv=[gate['python'],'-B','-u','-m','serve.server','--engine','strata','--config',str(run/'config.json'),'--host','127.0.0.1','--port','8748','--no-api-key','--no-fit-max-tokens','--offline','--ready-file',str(run/'ready.json')]
    state={'epoch':time.time(),'state':'starting','family':gate['family'],'worker_PID':os.getpid(),'server_argv':argv,'gate':gate,'before':before,'hardware_before':hardware,'jobs':[],'formal_calls_released':False}
    status=run/'status.json';save(status,state)
    server=None;child=None;binding=None;abort={};stop=threading.Event()

    def monitor():
        last=0
        with (run/'session-resources.jsonl').open('x') as f:
            while not stop.is_set():
                row=snapshot()
                if time.monotonic()-last>=10:
                    last=time.monotonic()
                    try:
                        row['admission_monitor']=inspect(binding) if binding else hardware_history(gate)
                        if binding is None:
                            assert not any(any(k in l.lower() for k in ['hardware error','machine check','soft-offlining','uncorrected']) for l in row['admission_monitor']['kernel_since_checkpoint'].splitlines())
                    except Exception as e:
                        row['monitor_failure']={'type':type(e).__name__,'text':str(e)}
                        abort.update(epoch=time.time(),reason='live_admission_monitor_failure',evidence=row['monitor_failure'])
                        if child is not None and child.poll() is None:os.killpg(child.pid,signal.SIGTERM)
                        if server is not None and server.poll() is None:server.terminate()
                f.write(json.dumps(row,ensure_ascii=False)+'\n');f.flush()
                ap=run/'ABORT.json'
                if ap.exists() and not abort:
                    abort.update(epoch=time.time(),reason='explicit_abort_file',content=ap.read_text())
                    if child is not None and child.poll() is None:os.killpg(child.pid,signal.SIGTERM)
                    if server is not None and server.poll() is None:server.terminate()
                stop.wait(2)

    thread=threading.Thread(target=monitor,daemon=True);thread.start()
    try:
        with (run/'server.stdout.log').open('x') as out,(run/'server.stderr.log').open('x') as err:
            server=subprocess.Popen(argv,cwd=gate['source_root'],env=env,stdout=out,stderr=err)
            state.update(server_PID=server.pid,state='loading');save(status,state)
            deadline=time.monotonic()+3600
            while not (run/'ready.json').exists():
                assert not abort,abort
                assert server.poll() is None,'Server exited before ready'
                assert time.monotonic()<deadline,'Startup deadline3600s'
                time.sleep(1)
            with urllib.request.urlopen('http://127.0.0.1:8748/metrics',timeout=30) as response:
                state['Linux_HTTPResponse_socket_deadline_supported']=isinstance(getattr(getattr(response.fp,'raw',None),'_sock',None),socket.socket)
                state['initial_metrics']=json.loads(response.read())
            assert state['Linux_HTTPResponse_socket_deadline_supported']
            assert state['initial_metrics']['engine']['max_context']==131072
            rows=processes();engine=[p for p,(a,parent) in rows.items() if parent==server.pid and Path(a[0]).resolve()==Path(cfg['exe']).resolve()]
            assert len(engine)==1,engine
            pid=engine[0];p=Path('/proc')/str(pid);raw=(p/'cmdline').read_bytes()
            binding={k:gate[k] for k in ['boot_id','known_HardwareCorrupted_kB','EDAC_controller_baseline','immutable_weight_bindings','run_root','SSD_device_number','kernel_checkpoint_epoch','known_corrected_history','RAS_baseline_max_ids','corrected_page_pfn']}
            binding.update(engine_PID=pid,engine_cmdline_SHA256=hashlib.sha256(raw).hexdigest(),engine_start_ticks=int((p/'stat').read_text().rsplit(') ',1)[1].split()[19]),engine_exe=cfg['exe'],server_PID=server.pid)
            save(run/'admission-binding.json',binding)
            state['positive_execution_host_guard']=inspect(binding)
            state.update(engine_PID=pid,actual_engine_argv=raw.decode().split('\0'),state='ready_awaiting_frozen_primary_release')
            save(status,state)
            release=run/'primary-release.json';deadline=time.monotonic()+3600
            while not release.exists():
                assert not abort,abort
                assert server.poll() is None,'Server exited while awaiting frozen release'
                assert time.monotonic()<deadline,'Primary frozen release deadline3600s; no calls sent'
                time.sleep(1)
            approved=json.loads(release.read_text());verify_freeze()
            assert approved['freeze_SHA256']==sha(HERE/'freeze.json') and approved['primary_actual_review']
            assert approved['binding_SHA256']==sha(run/'admission-binding.json')
            state.update(state='formal_serial_jobs_running',formal_calls_released=True,release=approved);save(status,state)
            env.update(EVAL_ENGINE_PID=str(pid),EVAL_ENGINE_EXE=cfg['exe'],EVAL_ENGINE_LOG=str(run/'engine.log'),EVAL_METRICS_URL='http://127.0.0.1:8748/metrics',EVAL_BASE_URL='http://127.0.0.1:8748/v1',EVAL_API_KEY='',EVAL_MODEL=cfg['model_name'],EVAL_PROFILE=gate['family'],EVAL_GUARD_COMMAND=json.dumps([gate['python'],'-B',str(HERE/'admission_guard.py'),'--binding',str(run/'admission-binding.json')]))
            for job in gate['registered_jobs']:
                assert not abort,abort
                assert server.poll() is None,'Server exited before the next unit'
                inspect(binding);verify_freeze()
                folder=run/'results';args=[gate['python'],'-B',str(HERE/job['script']),*job['args'],'--output',str(folder/job['category'])]
                item={'id':job['id'],'argv':args,'started_epoch':time.time()};state['jobs'].append(item);state['current_job']=job['id'];save(status,state)
                with (run/(job['id']+'.stdout.log')).open('x') as jo,(run/(job['id']+'.stderr.log')).open('x') as je:
                    child=subprocess.Popen(args,cwd=HERE,env=env,stdout=jo,stderr=je,start_new_session=True)
                    try:rc=child.wait(timeout=job['parent_timeout_s'])
                    except subprocess.TimeoutExpired:
                        os.killpg(child.pid,signal.SIGTERM);child.wait(timeout=10);raise RuntimeError('Retained runner deadline: '+job['id'])
                item.update(returncode=rc,finished_epoch=time.time());save(status,state)
                assert not abort,abort
                assert rc==0,('Runner failed; no automatic retry',item)
                result=folder/job['category']/job['result_relative']
                record=json.loads(result.read_text());item['result_path']=str(result);item['result_SHA256']=sha(result)
                assert not record.get('runtime_or_admission_failure'),('Retained runtime/admission failure',job['id'],record.get('error'))
                if job['category'] in ('long-horizon','long-context','speed'):
                    assert not record.get('error'),('Retained runtime failure',job['id'],record['error'])
                save(status,state)
            state['state']='all_registered_units_complete_pending_primary_review'
    except Exception as e:
        state.update(state='failed_retained_no_automatic_retry',exception={'type':type(e).__name__,'text':str(e),'traceback':traceback.format_exc()});raise
    finally:
        stop.set();thread.join(timeout=25)
        if child is not None and child.poll() is None:os.killpg(child.pid,signal.SIGTERM);child.wait(timeout=10)
        if server is not None and server.poll() is None:
            server.terminate()
            try:server.wait(timeout=45)
            except subprocess.TimeoutExpired:server.kill();server.wait()
        if profile.exists():
            with (run/'profile-after.bin').open('xb') as f:f.write(profile.read_bytes())
        state.update(finished_epoch=time.time(),after=snapshot(),abort=abort,server_exit_code=server.returncode if server else None)
        state['hardware_after']=hardware_history(gate)
        save(status,state)


if __name__=='__main__':main(Path(sys.argv[1]))
