"""Check public artifact boundaries without printing matched text."""
import re,json
from pathlib import Path
ROOT=Path(__file__).resolve().parent
bad=[];count=0
patterns=[r'sk-[A-Za-z0-9_-]{16,}',r'-----BEGIN (?:OPENSSH|RSA|EC|PRIVATE) PRIVATE KEY-----',r'192\.168\.\d+\.\d+',r'(?i)authorization\s*[:=]\s*[\x22\x27]?Bearer\s+[A-Za-z0-9_-]{16,}']
for p in ROOT.rglob('*'):
    if not p.is_file() or any(x in ['.git','__pycache__'] for x in p.parts):continue
    if p.suffix.lower() in ['.wav','.mp4','.safetensors','.hgn']:bad.append((str(p.relative_to(ROOT)),'private_or_large_asset'));continue
    if p.stat().st_size>5_000_000:bad.append((str(p.relative_to(ROOT)),'size_limit'));continue
    if p.suffix in ['.json','.py','.md','.txt','.html','.csv']:
        text=p.read_text(encoding='utf-8');count+=1
        if any(re.search(s,text) for s in patterns):bad.append((str(p.relative_to(ROOT)),'potential_secret_or_private_address'))
        if p.suffix=='.json':json.loads(text)
print(json.dumps({'text_files_checked':count,'findings':bad},ensure_ascii=False))
raise SystemExit(bool(bad))
