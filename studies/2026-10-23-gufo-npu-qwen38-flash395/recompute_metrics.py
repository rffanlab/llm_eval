"""Read-only NPU analysis; exact Gufo native counters, frozen grades unchanged."""
import copy
import hashlib
import importlib.util
import json
from pathlib import Path
import re
import statistics

W = Path(__file__).resolve().parent
ROOT = W.parents[1]
spec = importlib.util.spec_from_file_location('shared_analysis', W / 'analysis_helpers.py')
base = importlib.util.module_from_spec(spec)
spec.loader.exec_module(base)
read = lambda p: json.loads(p.read_text(encoding='utf-8'))

def latency_fields(row, turns):
    first = turns[0] if turns else {}
    times = [first.get(k) for k in ['first_reasoning_s', 'first_content_s', 'first_tool_s']]
    row['first_actual_token_s'] = min((x for x in times if isinstance(x, (int, float))), default=None)
    row['first_content_s'] = first.get('first_content_s')
    row['first_tool_s'] = first.get('first_tool_s')
    return row

def main():
    source = W
    progress = read(source / 'suite-progress.json')
    assert progress['finished'] and len(progress['completed']) == 87
    reviews_path = W / 'editorial-review.json'
    reviews = read(reviews_path)
    by_sha = {v['answer_sha256']: v for v in reviews['reviews'].values()}
    result = {'method': 'Gufo prompt_n/prompt_ms and predicted_n/predicted_ms; sum calls within round, then median; frozen grades retained', 'conditions': {}}
    for label in ['gpu-only', 'npu-slice', 'npu-two-bank']:
        folder = source / 'results' / label
        launch = read(source / 'conditions' / label / 'launch.json')
        c = {'lane': 'gufo', 'short': {}, 'depth_diagnostic': {}, 'long_horizon': {}, 'long_context': {}, 'speed_probes': {}, 'load_ready_s': launch['load_ready_s']}
        groups = {}
        for path in sorted((folder / 'short').rglob('result.json')):
            r = read(path)
            row = base.work_unit(r, r['turns'], 'gufo', r['elapsed_s'], r['grade']['pass'])
            latency_fields(row, r['turns'])
            row['result_file'] = path.relative_to(source / 'results').as_posix()
            if r['task'].startswith('W'):
                digest = hashlib.sha256(r['content'].encode()).hexdigest()
                assert digest in by_sha, 'Unreviewed writing answer'
                review = copy.deepcopy(by_sha[digest])
                reviews['reviews'].setdefault(row['result_file'], review)
                row['editorial'] = base.editorial_review(review, r['content'])
                row['automatic_format_pass'] = row['strict_pass']
                row['strict_pass'] = bool(row['automatic_format_pass'] and row['editorial']['pass'])
            row['unauthorized_tool_attempt'] = any(x.get('name') == 'restart_production' for x in r.get('tool_trace', []))
            row['answer_sha256'] = hashlib.sha256(r.get('content', '').encode()).hexdigest()
            row['resources'] = base.resources(path.parent / 'resources.jsonl')
            groups.setdefault((r['variant'], r['task']), []).append(row)
        for (variant, task), rows in groups.items():
            c['short' if variant == 'main' else 'depth_diagnostic'][task] = base.summarize(rows)
        episodes, stages = [], {}
        for path in sorted((folder / 'long').rglob('record.json')):
            r = read(path)
            row = base.work_unit(r, [t for s in r['stages'] for t in s['turns']], 'gufo', r['elapsed_s'], r['complete_delivery'])
            latency_fields(row, [t for s in r['stages'] for t in s['turns']])
            row.update(result_file=path.relative_to(source / 'results').as_posix(), stage_grades=[s['grade'] for s in r['stages']])
            memo = read(path.parent / 'snapshots/S4.json')['files']['delivery.md']
            digest = hashlib.sha256(memo.encode()).hexdigest()
            assert digest in by_sha, 'Unreviewed delivery memo'
            review = copy.deepcopy(by_sha[digest])
            reviews['reviews'].setdefault(row['result_file'], review)
            row['delivery_memo_editorial'] = base.editorial_review(review, memo)
            row['final_artifacts_correct'] = all(x['pass'] for x in r['stages'][-1]['grade']['checks'] if x['name'] != 'failure_recovery')
            row['resources'] = base.resources(path.parent / 'resources.jsonl')
            episodes.append(row)
            for s in r['stages']:
                sr = {'round': r['round'], 'error': s.get('error'), 'grade': s['grade']}
                strict = bool(s['grade']['pass'] and s['finished_with_answer'] and not s.get('error'))
                unit = base.work_unit(sr, s['turns'], 'gufo', s['elapsed_s'], strict)
                latency_fields(unit, s['turns'])
                unit.update(stage_grade=s['grade'], finished_with_answer=s['finished_with_answer'])
                stages.setdefault(s['id'], []).append(unit)
        c['long_horizon'] = {'episode': base.summarize(episodes), 'stages': {k: base.summarize(v) for k, v in stages.items()}}
        for dirname, target in [('context', 'long_context'), ('speed', 'speed_probes')]:
            grouped = {}
            for path in sorted((folder / dirname).rglob('result.json')):
                r = read(path); response = r['response']
                elapsed = r['elapsed_s'] if dirname == 'context' else r['latency']['api_elapsed_s']
                row = base.work_unit(r, [{'usage': response['usage'], 'timings': response['timings']}], 'gufo', elapsed, r.get('complete_hard'))
                row['result_file'] = path.relative_to(source / 'results').as_posix()
                row['actual_prompt_tokens'] = r.get('actual_prompt_tokens')
                if dirname == 'context':
                    assert r['length_qualified'] and r['actual_prompt_tokens'] > 100000
                row['ttft_s'] = r['latency'].get('first_reasoning_s') or r['latency'].get('first_content_s')
                grouped.setdefault(r.get('task', r.get('kind')), []).append(row)
            c[target] = {k: base.summarize(v) for k, v in grouped.items()}
        c['quality_summary'] = base.quality_summary(c)
        c['quality_summary']['recommendation_pending_primary_review'] = False
        log = (source / 'conditions' / label / 'service-counters-redacted.log').read_bytes()
        observed = [int(x) for x in re.findall(rb'npu stats: (\d+) layers', log)]
        c['npu_observed_wait_count_lower_bound'] = max(observed, default=0)
        samples = [json.loads(x) for x in (source / 'conditions' / label / 'telemetry.jsonl').read_text().splitlines()]
        c['sampled_resources'] = {'samples': len(samples), 'mem_available_min_bytes': min(x['MemAvailable_bytes'] for x in samples), 'vram_peak_bytes': max(g['mem_info_vram_used'] for x in samples for g in x['gpu']), 'gtt_peak_bytes': max(g['mem_info_gtt_used'] for x in samples for g in x['gpu']), 'sampling_seconds': 2}
        c['npu_dispatch_by_case'] = {}
        for unit in [x for x in progress['completed'] if x['condition'] == label]:
            def counter(offset):
                values = re.findall(rb'npu stats: (\d+) layers', log[:offset])
                return int(values[-1]) if values else 0
            a, b = counter(unit['engine_log_start_byte']), counter(unit['engine_log_end_byte'])
            delta = b - a
            c['npu_dispatch_by_case'][unit['name']] = {'printed_counter_delta': delta, 'wait_count_lower_bound': max(0, delta - 35), 'wait_count_upper_bound': delta + 35, 'exact_count': False}
        result['conditions'][label] = c
    (W / 'metrics-recomputed.json').write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    for label, c in result['conditions'].items():
        print(json.dumps({'condition': label, 'quality': c['quality_summary'], 'speed': {k: {x: v[x] for x in ['prefill_median_tokens_s', 'decode_median_tokens_s', 'elapsed_median_s']} for k, v in c['speed_probes'].items()}, 'context': {k: {x: v[x] for x in ['strict_passes', 'prefill_median_tokens_s', 'decode_median_tokens_s', 'elapsed_median_s']} for k, v in c['long_context'].items()}, 'npu_wait_lower_bound': c['npu_observed_wait_count_lower_bound']}, ensure_ascii=False))

if __name__ == '__main__':
    main()
