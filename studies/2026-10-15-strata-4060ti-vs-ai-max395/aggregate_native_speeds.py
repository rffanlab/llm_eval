"""Post-run reporting only. Preserve every call and grade, append native speed tables."""
from pathlib import Path
import csv
import hashlib
import json
import sys

S = Path(__file__).resolve().parent
sys.path.insert(0, str(S.parents[1]))
from metrics.native_speed import aggregate_turns, summarize_rounds


def build():
    groups = {}
    unique_calls = 0

    def add(profile, group, round_no, turns, source):
        groups.setdefault(group, {}).setdefault(profile, {'rounds': []})['rounds'].append({
            'round': round_no, 'source': source.relative_to(S).as_posix(),
            'source_sha256': hashlib.sha256(source.read_bytes()).hexdigest(),
            'native_speed': aggregate_turns(turns)})

    for path in sorted((S/'results/short').rglob('result.json')):
        r = json.loads(path.read_text(encoding='utf-8'))
        group = r['variant']+'/'+r['task']
        add(r['profile'], group, r['round'], r['turns'], path)
        unique_calls += len(r['turns'])
    for path in sorted((S/'results/long').rglob('record.json')):
        r = json.loads(path.read_text(encoding='utf-8'))
        turns = [t for stage in r['stages'] for t in stage['turns']]
        add(r['profile'], 'long/ALL', r['round'], turns, path)
        unique_calls += len(turns)
        for stage in r['stages']:
            add(r['profile'], 'long/'+stage['id'], r['round'], stage['turns'], path)
    for path in sorted((S/'results/speed').rglob('result.json')):
        r = json.loads(path.read_text(encoding='utf-8'))
        add(r['profile'], 'speed/'+r['kind'], r['round'], [r['response']], path)
        unique_calls += 1
    for profiles in groups.values():
        for item in profiles.values():
            item.update(summarize_rounds(item['rounds']))
    return {'study': S.name, 'unique_formal_API_calls': unique_calls,
            'unit': 'token/s', 'formula': 'per round: sum(prompt_n)*1000/sum(prompt_ms); sum(predicted_n)*1000/sum(predicted_ms). Then median across rounds.',
            'input_scope': 'Native newly evaluated prompt_n. Reused cache_n excluded from numerator and reported separately.',
            'output_scope': 'Native predicted_n, including generated thinking/body/tool arguments as measured by engine.',
            'time_scope': 'Native compute timers. API/tool/full-work wait is separate; not an estimate from wall time.',
            'missing': 'Any missing native call or nonpositive timer makes that work-round speed unknown, never zero.',
            'group_scope': 'Long stages and whole episodes overlap; do not add group call counts. No new inference or rescoring.',
            'groups': groups}


def main():
    f = json.loads((S/'freeze.json').read_text(encoding='utf-8'))['files']
    assert all(hashlib.sha256((S/name).read_bytes()).hexdigest() == sha for name, sha in f.items())
    d = build()
    assert d['unique_formal_API_calls'] == 223
    (S/'native-speeds.json').write_text(json.dumps(d, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
    rows = []
    for group, profiles in d['groups'].items():
        for profile, data in profiles.items():
            for row in data['rounds']:
                rows.append(dict(group=group, profile=profile, round=row['round'],
                                 source=row['source'], source_sha256=row['source_sha256'], **row['native_speed']))
    with (S/'native-speeds.csv').open('w', encoding='utf-8', newline='') as out:
        w = csv.DictWriter(out, fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)
    assert all(x['prefill_tokens_s'] is not None and x['decode_tokens_s'] is not None for x in rows)
    print(json.dumps({'native_calls': 223, 'work_round_or_probe_rows': len(rows),
                      'all_native_timings_complete': True, 'frozen_files_unchanged': len(f)}, ensure_ascii=False))


if __name__ == '__main__':
    main()
