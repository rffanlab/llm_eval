"""Aggregate preserved records; never calls a model or changes a raw result."""
import hashlib
import json
import statistics
from pathlib import Path

HERE = Path(__file__).resolve().parent
PROFILES = ['rtx4060ti', 'ai-max395']
TASKS = ['D01', 'C01', 'W01', 'A01', 'C03', 'A02', 'W03']


def read(path):
    return json.loads(path.read_text(encoding='utf-8'))


def median(values):
    values = [x for x in values if isinstance(x, (int, float))]
    return statistics.median(values) if values else None


def usage_known(record, turns):
    """A length stop has final usage; an interrupted HTTP call may not have it."""
    accounted_errors = {None, 'output_truncated', 'agent_reply_budget_exhausted',
                        'one_tool_per_reply_required', 'unexpected_tool_call',
                        'total_output_budget_exhausted', 'task_wall_budget'}
    if not turns or record.get('error') not in accounted_errors:
        return False
    keys = ['prompt_tokens', 'completion_tokens', 'total_tokens']
    return all(isinstance((t.get('usage') or {}).get(k), int) for t in turns for k in keys) and all(
        sum(t['usage'][k] for t in turns) == record['usage'][k] for k in keys)


def review_for(reviews, profile, task, round_no, content):
    digest = hashlib.sha256(content.encode()).hexdigest()
    rows = [x for x in reviews if (x['profile'], x['task'], x['round']) == (profile, task, round_no)]
    assert len(rows) <= 1, 'duplicate editorial review'
    if not rows:
        return None
    assert rows[0]['content_sha256'] == digest, 'editorial review does not match artifact'
    return rows[0]


def resources(root):
    rows = []
    for p in root.rglob('resources.jsonl'):
        for line in p.read_text().splitlines():
            if line.strip():
                rows.append(json.loads(line))
    values = [r['MemAvailable'] for r in rows if 'MemAvailable' in r]
    gpu = {}
    for row in rows:
        for item in row.get('gpu', []):
            label = item.get('pci', item.get('uuid', item.get('backend', 'unknown')))
            dst = gpu.setdefault(label, {'backend': item.get('backend')})
            for key in ['VRAM', 'GTT', 'VRAM_total', 'GTT_total']:
                if isinstance(item.get(key), (int, float)):
                    dst[key + '_max_bytes'] = max(dst.get(key + '_max_bytes', 0), item[key])
    return {'samples': len(rows), 'MemAvailable_min_bytes': min(values) if values else None,
            'MemAvailable_median_bytes': median(values), 'GPU': gpu,
            'caution': 'Unified RAM/GTT overlap; do not add them. Sampling is approximate at 2 seconds.'}


def main():
    for name, digest in read(HERE / 'freeze.json')['files'].items():
        assert hashlib.sha256((HERE / name).read_bytes()).hexdigest() == digest, name
    reviews = read(HERE / 'editorial-review.json')['reviews']
    output = {'study': HERE.name, 'model': 'Qwen3.8 Next Flash', 'quantization': 'UD-Q4_K_XL',
              'engine': 'Strata v0.1.44.1', 'profiles': {},
              'scope': 'Two physical computers, not an isolated GPU comparison. n=2 work tasks; n=3 speed probes.'}
    for profile in PROFILES:
        base = HERE / 'results'
        result = {'tasks': {}, 'depth': [], 'speed': {}, 'long_horizon': []}
        for variant in ['main', 'depth']:
            for task in TASKS if variant == 'main' else ['D01']:
                records = []
                for p in sorted((base / 'short' / profile / variant / 'local').glob(task + '-r*/result.json')):
                    r = read(p)
                    review = review_for(reviews, profile, task, r['round'], r['content']) if task in ['W01', 'W03'] else None
                    untruncated = all(x.get('finish_reason') != 'length' for x in r.get('turns', []))
                    complete = bool(r.get('grade', {}).get('pass')) and not r.get('error') and untruncated
                    if task in ['W01', 'W03']:
                        complete = complete and bool(review and review['pass'])
                    records.append({'round': r['round'], 'source': p.relative_to(HERE).as_posix(),
                                    'elapsed_s': r['elapsed_s'], 'usage': r['usage'],
                                    'usage_complete': r['usage_complete'], 'hard_pass': r.get('grade', {}).get('pass', False),
                                    'usage_known_by_turn_audit': usage_known(r, r.get('turns', [])),
                                    'editorial_score': review['total'] if review else None,
                                    'editorial_pending': task in ['W01', 'W03'] and review is None,
                                    'complete_delivery': complete, 'untruncated': untruncated,
                                    'reasoning_chars': r.get('reasoning_chars'),
                                    'first_content_s': [t.get('first_content_s') for t in r.get('turns', [])],
                                    'turns': len(r.get('turns', [])), 'error': r.get('error')})
                if variant == 'depth':
                    result['depth'] = records
                else:
                    result['tasks'][task] = {'rounds': records, 'observed': len(records), 'expected': 2,
                                            'complete_deliveries': sum(x['complete_delivery'] for x in records),
                                            'elapsed_median_s': median([x['elapsed_s'] for x in records]),
                                            'output_tokens_median': median([x['usage']['completion_tokens'] for x in records])}
        for kind in ['short512', 'prompt4k', 'prompt32k']:
            rows = []
            for p in sorted((base / 'speed' / profile).glob(kind + '-r*/result.json')):
                r = read(p)
                response = r.get('response', {})
                rows.append({'round': r['round'], 'source': p.relative_to(HERE).as_posix(),
                             'latency': r.get('latency'), 'timings': response.get('timings'),
                             'usage': response.get('usage'), 'error': r.get('error')})
            result['speed'][kind] = {'rounds': rows, 'expected': 3, 'observed': len(rows),
                                    'decode_median_tokens_s': median([(x.get('timings') or {}).get('predicted_per_second') for x in rows]),
                                    'prefill_median_tokens_s': median([(x.get('timings') or {}).get('prompt_per_second') for x in rows]),
                                    'api_elapsed_median_s': median([(x.get('latency') or {}).get('api_elapsed_s') for x in rows])}
        for p in sorted((base / 'long' / profile).glob('r*/record.json')):
            r = read(p)
            # The authoritative in-memory text is preserved in the final stage snapshot.
            snapshot = p.parent / 'snapshots' / 'S4.json'
            text = read(snapshot)['files'].get('delivery.md', '') if snapshot.exists() else ''
            review = review_for(reviews, profile, 'LH01', r['round'], text)
            result['long_horizon'].append({'round': r['round'], 'source': p.relative_to(HERE).as_posix(),
                                          'elapsed_s': r.get('elapsed_s'), 'usage': r['usage'],
                                          'usage_complete': r['usage_complete'], 'tool_calls': r.get('tool_calls'),
                                          'usage_known_by_turn_audit': usage_known(r, [t for s in r['stages'] for t in s['turns']]),
                                          'hard_complete_delivery': r.get('complete_delivery', False),
                                          'editorial_score': review['total'] if review else None,
                                          'editorial_pending': review is None,
                                          'complete_delivery': bool(r.get('complete_delivery') and review and review['pass']),
                                          'stages': [{'id': s['id'], 'name': s['name'], 'elapsed_s': s.get('elapsed_s'),
                                                      'hard_pass': s.get('grade', {}).get('pass', False),
                                                      'checks': s.get('grade'), 'finished_with_answer': s.get('finished_with_answer'),
                                                      'error': s.get('error')} for s in r['stages']],
                                          'error': r.get('error')})
        main_rows = [r for task in result['tasks'].values() for r in task['rounds']]
        result['observed_main_cases'] = len(main_rows)
        result['expected_main_cases'] = 14
        result['complete_main_deliveries'] = sum(x['complete_delivery'] for x in main_rows)
        result['main_usage_sum'] = {k: sum(x['usage'][k] for x in main_rows) for k in ['prompt_tokens', 'completion_tokens', 'total_tokens']}
        result['main_usage_complete_by_turn_audit'] = bool(main_rows) and all(x['usage_known_by_turn_audit'] for x in main_rows)
        result['token_scope'] = 'API-reported prompt/output token sums, including failed attempts; not unique input tokens. Interrupted calls without final usage remain unknown.'
        result['resources_short_and_depth'] = resources(base / 'short' / profile)
        result['resources_long'] = resources(base / 'long' / profile)
        result['complete_collection'] = (len(main_rows) == 14 and len(result['depth']) == 2
                                         and all(x['observed'] == 3 for x in result['speed'].values())
                                         and len(result['long_horizon']) == 2
                                         and all('elapsed_s' in x and x['elapsed_s'] is not None for x in result['long_horizon'])
                                         and not any(x['editorial_pending'] for x in result['long_horizon'])
                                         and not any(x['editorial_pending'] for x in main_rows))
        output['profiles'][profile] = result
    output['complete_collection'] = all(x['complete_collection'] for x in output['profiles'].values())
    (HERE / 'summary.json').write_text(json.dumps(output, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({'complete_collection': output['complete_collection'], 'profiles': {
        k: {'main_cases': v['observed_main_cases'], 'complete_deliveries': v['complete_main_deliveries'],
            'long_episodes': len(v['long_horizon'])} for k, v in output['profiles'].items()}}, ensure_ascii=False))


if __name__ == '__main__':
    main()
