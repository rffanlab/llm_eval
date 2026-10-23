"""Portable Linux registration/guard for manual reproduction; no credentials logged."""
import argparse
import hashlib
import json
from pathlib import Path


def process(pid):
    root = Path('/proc') / str(pid)
    raw = (root / 'cmdline').read_bytes()
    assert raw, 'registered process exited'
    return {'pid':pid,'argv_sha256':hashlib.sha256(raw).hexdigest(),
            'executable':str((root/'exe').resolve())}


def snapshot():
    found = []
    downloads = []
    for p in Path('/proc').glob('[0-9]*'):
        try:
            args = [s.decode() for s in (p/'cmdline').read_bytes().split(b'\0') if s]
            state = (p/'stat').read_text().split()[2]
        except (OSError,UnicodeError):
            continue
        if not args or state == 'Z':
            continue
        if Path(args[0]).name in ['strata','gufo','llama-server','flash_serve','ollama'] or 'serve.server' in args:
            found.append(int(p.name))
        if Path(args[0]).name == 'aria2c' and state not in ['T','t']:
            downloads.append(int(p.name))
    mem = next(int(x.split()[1])*1024 for x in Path('/proc/meminfo').read_text().splitlines() if x.startswith('MemAvailable:'))
    power = {str(p):int(p.read_text()) for p in Path('/sys/class/drm').glob('card[0-9]*/device/hwmon/hwmon*/power1_cap')}
    return {'boot_id':Path('/proc/sys/kernel/random/boot_id').read_text().strip(),
            'engine_pids':found,'active_aria2_pids':downloads,'MemAvailable_bytes':mem,'power_caps_uw':power}


def main(a):
    state = snapshot()
    if a.action == 'register':
        assert set(state['engine_pids']) == set(a.pid), 'exactly the registered inference processes must be active'
        assert not state['active_aria2_pids'], 'finish or pause acquisitions before timing'
        manifest = json.loads(Path(a.candidates).read_text())
        e = next(e for e in manifest['candidates'] if e['deployment_label'] == a.candidate)
        weights = []
        for f in e['files']:
            p = Path(a.model_dir) / Path(f['path']).name
            st = p.stat()
            assert st.st_size == f['bytes']
            with p.open('rb') as stream:
                got = hashlib.file_digest(stream,'sha256').hexdigest()
            assert got == f['sha256'], 'weights differ from the pinned candidate'
            weights.append({'path':str(p.resolve()),'size':st.st_size,'mtime_ns':st.st_mtime_ns,'sha256':got})
        d = {**state,'candidate':e['deployment_label'],'processes':[process(pid) for pid in a.pid],
             'weights':weights,'minimum_available_bytes':8*2**30}
        out = Path(a.registration)
        assert not out.exists(), 'preserve an existing registration'
        out.write_text(json.dumps(d,indent=2)+'\n')
    else:
        d = json.loads(Path(a.registration).read_text())
        assert d['boot_id'] == state['boot_id'], 'boot changed; diagnose before resuming'
        assert set(d['engine_pids']) == set(state['engine_pids']), 'another inference process is active or the engine restarted'
        assert not state['active_aria2_pids'], 'active acquisition'
        assert state['MemAvailable_bytes'] >= d['minimum_available_bytes']
        assert state['power_caps_uw'] == d['power_caps_uw'], 'power limit changed'
        for p in d['processes']:
            assert process(p['pid']) == p, 'process identity changed'
        for f in d['weights']:
            st = Path(f['path']).stat()
            assert st.st_size == f['size'] and st.st_mtime_ns == f['mtime_ns'], 'weights changed'
    print(json.dumps(state))


if __name__ == '__main__':
    p = argparse.ArgumentParser()
    p.add_argument('action',choices=['register','verify'])
    p.add_argument('--registration',required=True)
    p.add_argument('--pid',type=int,nargs='+')
    p.add_argument('--model-dir')
    p.add_argument('--candidate')
    p.add_argument('--candidates',default=str(Path(__file__).with_name('candidates.json')))
    main(p.parse_args())
