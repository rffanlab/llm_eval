"""Read-only post-run audit of final artifacts; no new model calls or rescoring."""
from pathlib import Path
import json,hashlib
S=Path(__file__).resolve().parent
def main():
 rows=[]
 summary=json.loads((S/'summary.json').read_text(encoding='utf-8')); assert summary.get('results_complete') is True and summary.get('all_editorial_complete') is True
 profiles=list(summary['phases']['validate'])
 for profile in profiles:
  for rnd in [1,2]:
   base=S/'results/validate/long'/profile/('r'+str(rnd))
   missing=[]
   def load(path):
    if not path.exists():missing.append(path.relative_to(S).as_posix());return None
    try:return json.loads(path.read_text(encoding='utf-8'))
    except (ValueError,TypeError):missing.append(path.relative_to(S).as_posix()+' (invalid JSON)');return None
   d=load(base/'record.json');snap=load(base/'snapshots/S4.json');release=base/'workspace/release'
   manifest=load(release/'manifest.json');summary=load(release/'summary.json')
   report_path=base/'workspace/delivery.md'
   report=report_path.read_text(encoding='utf-8') if report_path.exists() else (missing.append(report_path.relative_to(S).as_posix()) or '')
   publication=(snap or {}).get('publication') or {}
   hashes={}
   for name,digest in ((manifest or {}).get('sha256') or {}).items():
    path=release/name
    hashes[name]=path.exists() and hashlib.sha256(path.read_bytes()).hexdigest()==digest
    if not path.exists():missing.append(path.relative_to(S).as_posix())
   stages=(d or {}).get('stages') or []
   checks={c['name']:c['pass'] for c in (stages[-1].get('grade',{}).get('checks',[]) if stages else [])}
   # Functional/publication and report/budget outcomes remain separate.
   artifact_missing=[x for x in missing if not x.endswith('/workspace/delivery.md')]
   final_ok=not artifact_missing and publication.get('dataset')=='final' and (manifest or {}).get('dataset')=='final' and bool(hashes) and all(hashes.values()) and checks.get('current_publication_final') is True and checks.get('manifest_matches_bytes') is True and checks.get('final_release_exact') is True
   row={'profile':profile,'round':rnd,'final_release_matches_expected':final_ok,'missing':missing,'dataset':(manifest or {}).get('dataset'),'file_sha256_matches':hashes,
    'summary':summary,'report_nonspace_chars':len(''.join(report.split())),
    'report_hard_checks':{k:v for k,v in checks.items() if k.startswith('report') or k=='length_400_900'},
    'stage_errors':{s.get('id'):s.get('error') for s in stages},'registered_complete_delivery':(d or {}).get('complete_delivery'),
    'source':(base/'record.json').relative_to(S).as_posix()}
   rows.append(row)
 (S/'final-release-audit.json').write_bytes((json.dumps({'definition':'Additive byte/manifest and publication audit; does not replace frozen stage, report, or budget grades.','episodes':rows},ensure_ascii=False,indent=2)+'\n').encode())
 print(json.dumps({'episodes':len(rows),'final_releases_correct':sum(r['final_release_matches_expected'] for r in rows)}))
if __name__=='__main__':main()
