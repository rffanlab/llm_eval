"""Read-only compatibility checks. Supply already installed files; no downloads."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess

p = argparse.ArgumentParser()
p.add_argument('--gufo', required=True, help='Unmodified Gufo v0.20.0 binary')
p.add_argument('--halogen-entrypoint', required=True, help='deploy/entrypoint.sh from the pinned Halogen v0.18.13 commit')
a = p.parse_args()
binary = Path(a.gufo).resolve()
entrypoint = Path(a.halogen_entrypoint).resolve()
raw = entrypoint.read_bytes()
assert hashlib.sha256(raw).hexdigest() == '55f1b91e460988754468dfcde1c760201cf896386caf305805c21b337ead7c1c', 'different upstream entrypoint'
text = raw.decode()
start = text.index('host_preflight() {')
end = text.index('\n}\n', start) + 3
function = text[start:end]
records = []
for label, command in [('Gufo version', [str(binary), '--version']), ('Gufo GPU diagnostics', [str(binary), 'diagnose', '--json', '--section', 'gpu']), ('Halogen original host_preflight only', ['/bin/bash', '-c', function + '\nhost_preflight\n'])]:
    done = subprocess.run(command, capture_output=True, text=True, timeout=30)
    records.append({'check': label, 'exit_code': done.returncode, 'stdout': done.stdout, 'stderr': done.stderr})
print(json.dumps({'model_target': 'Qwen3.8 Next Flash', 'model_loaded_by_this_script': False, 'records': records}, ensure_ascii=False, indent=2))
