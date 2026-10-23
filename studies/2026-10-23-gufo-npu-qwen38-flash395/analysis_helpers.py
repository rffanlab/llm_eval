"""Read-only analysis of frozen outputs; never rewrites a model result.

Usage: python aggregate.py --results /path/to/results --output metrics.json
Editorial scores are deliberately separate: automatic writing checks do not
establish writing quality or the final recommendation.
"""
import argparse
import copy
import hashlib
import json
import math
from pathlib import Path
import statistics


def numeric(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def median_complete(values):
    values = list(values)
    return statistics.median(values) if values and all(numeric(x) for x in values) else None


def native(turns, lane):
    """Sum native work and native milliseconds before computing any rate."""
    turns = list(turns)
    out = {'calls': len(turns)}
    for label, nk, tk in [('prefill', 'prompt_n', 'prompt_ms'),
                          ('decode', 'predicted_n', 'predicted_ms')]:
        pairs = []
        for turn in turns:
            t = turn.get('timings') or {}
            n, ms = t.get(nk), t.get(tk)
            if not (numeric(n) and numeric(ms) and n >= 0 and ms >= 0):
                continue
            if lane == 'common' and label == 'decode':
                # b11829 server-common.h: the first token uses prompt logits.
                n = max(n - 1, 0)
            if ms > 0 or n == 0:
                pairs.append((n, ms))
        complete = bool(turns) and len(pairs) == len(turns)
        n, ms = sum(x[0] for x in pairs), sum(x[1] for x in pairs)
        out.update({label + '_timing_complete': complete,
                    label + '_calls_measured': len(pairs),
                    label + '_tokens_measured': n,
                    label + '_ms_measured': ms,
                    label + '_tokens_s': n * 1000 / ms if complete and n > 0 and ms > 0 else None})
    cache = [(x.get('timings') or {}).get('cache_n') for x in turns]
    out['cached_tokens'] = sum(cache) if cache and all(numeric(x) and x >= 0 for x in cache) else None
    return out


def usage(turns):
    out = {}
    for key in ['prompt_tokens', 'completion_tokens', 'total_tokens']:
        values = [(x.get('usage') or {}).get(key) for x in turns]
        out[key] = sum(values) if values and all(numeric(v) and v >= 0 for v in values) else None
    return out


def resources(path):
    """Keep sampled resource summaries distinct from instantaneous admissions."""
    if not path.exists():
        return None
    rows = []
    for line in path.read_text(encoding='utf-8').splitlines():
        try:
            rows.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    used = [r['MemTotal'] - r['MemAvailable'] for r in rows
            if numeric(r.get('MemTotal')) and numeric(r.get('MemAvailable'))]
    vram = [g['VRAM'] for r in rows for g in r.get('gpu', []) if numeric(g.get('VRAM'))]
    gtt = [g['GTT'] for r in rows for g in r.get('gpu', []) if numeric(g.get('GTT'))]
    return {'samples': len(rows),
            'system_used_peak_bytes': max(used) if used else None,
            'vram_peak_bytes': max(vram) if vram else None,
            'gtt_peak_bytes': max(gtt) if gtt else None,
            'note': '2-second samples; system used means MemTotal minus MemAvailable, not model-exclusive RSS'}


def work_unit(record, turns, lane, elapsed, strict):
    return {'round': record.get('round'), 'elapsed_s': elapsed,
            'strict_pass': strict, 'error': record.get('error'),
            'usage': usage(turns), 'native': native(turns, lane),
            'reasoning_chars': sum(x.get('reasoning_chars', 0) for x in turns),
            'grade': copy.deepcopy(record.get('grade'))}


def summarize(rows):
    return {'rounds': len(rows),
            'strict_passes': sum(x['strict_pass'] is True for x in rows),
            'strict_known_rounds': sum(isinstance(x['strict_pass'], bool) for x in rows),
            'elapsed_median_s': median_complete(x['elapsed_s'] for x in rows),
            'prefill_median_tokens_s': median_complete(x['native']['prefill_tokens_s'] for x in rows),
            'decode_median_tokens_s': median_complete(x['native']['decode_tokens_s'] for x in rows),
            'api_prompt_median_tokens': median_complete(x['usage']['prompt_tokens'] for x in rows),
            'api_completion_median_tokens': median_complete(x['usage']['completion_tokens'] for x in rows),
            'api_total_median_tokens': median_complete(x['usage']['total_tokens'] for x in rows),
            'cache_median_tokens': median_complete(x['native']['cached_tokens'] for x in rows),
            'raw_rounds': rows}


def load(path):
    return json.loads(path.read_text(encoding='utf-8'))


def editorial_review(review, answer):
    """A review is accepted only for the exact answer bytes it inspected."""
    if review is None:
        return None
    assert review['answer_sha256'] == hashlib.sha256(answer.encode()).hexdigest(), 'review/answer mismatch'
    scores = review['scores']
    assert set(scores) == {'facts', 'completeness', 'clarity', 'usability'}
    assert all(isinstance(x, int) and not isinstance(x, bool) and 0 <= x <= 5 for x in scores.values())
    assert isinstance(review['critical_fact_error'], bool)
    assert isinstance(review['rationale'], str) and review['rationale'].strip()
    result = copy.deepcopy(review)
    result['total_out_of_20'] = sum(scores.values())
    result['pass'] = (result['total_out_of_20'] >= 16 and scores['facts'] >= 3
                      and not review['critical_fact_error'])
    return result


def quality_summary(condition):
    """Frozen weights; missing editorial evidence stays unknown."""
    short = condition['short']
    names = ['D01', 'C01', 'W01', 'A01', 'C03', 'A02', 'W03']
    rows_complete = all(t in short and short[t]['rounds'] == 2 for t in names)
    units = [r for x in short.values() for r in x['raw_rounds']]
    out = {'short_rows_observed': len(units), 'short_rows_expected': 14,
           'strict_passes': sum(r['strict_pass'] is True for r in units),
           'strict_known_rows': sum(isinstance(r['strict_pass'], bool) for r in units),
           'unauthorized_tool_attempt': any(r.get('unauthorized_tool_attempt') for r in units),
           'recommendation_pending_primary_review': True}
    known = rows_complete and out['strict_known_rows'] == 14
    out['routine_gate_pass'] = (out['strict_passes'] >= 12 and not out['unauthorized_tool_attempt']) if known else None
    waits = [short[t]['elapsed_median_s'] for t in names] if rows_complete else []
    out['seven_task_wait_geomean_s'] = math.exp(statistics.mean(math.log(x) for x in waits)) if waits and all(numeric(x) and x > 0 for x in waits) else None
    def task_score(task):
        if task not in short or short[task]['rounds'] != 2:
            return None
        rows = short[task]['raw_rounds']
        if task.startswith('W'):
            vals = [r.get('editorial', {}).get('total_out_of_20') if r.get('editorial') else None for r in rows]
            return statistics.mean(vals) * 5 if all(numeric(x) for x in vals) else None
        vals = [(r.get('grade') or {}).get('score') for r in rows]
        return statistics.mean(vals) if all(numeric(x) for x in vals) else None
    components = {}
    for label, ids, weight in [('code', ['C01', 'C03'], .30),
                                ('agent', ['A01', 'A02'], .25),
                                ('writing_editorial', ['W01', 'W03'], .20)]:
        vals = [task_score(t) for t in ids]
        components[label] = statistics.mean(vals) * weight if all(numeric(x) for x in vals) else None
    components['extraction'] = short['D01']['strict_passes'] / 2 * 10 if 'D01' in short and short['D01']['rounds'] == 2 else None
    long = condition['long_horizon']
    episodes = long.get('episode', {}).get('raw_rounds', [])
    if len(episodes) == 2:
        # Four stages are equal-weight; a stage not reached in a failed
        # episode contributes zero, rather than disappearing from the mean.
        stage_scores = []
        for row in episodes:
            grades = row['stage_grades']
            values = [g['passed'] / g['total'] if g and g.get('total') else 0 for g in grades]
            stage_scores.append(sum(values) / 4)
        components['long_horizon'] = statistics.mean(stage_scores) * 15
    else:
        components['long_horizon'] = None
    out['quality_points'] = components
    out['quality_total_out_of_100'] = sum(components.values()) if all(numeric(x) for x in components.values()) else None
    return out


def analyze(root, reviews=None):
    reviews = reviews or {}
    result = {'method': 'native sums within round, then medians across all observed rounds',
              'writing_editorial_review_required': True, 'conditions': {}}
    for folder in sorted(root.iterdir()):
        if not folder.is_dir() or not (folder / 'launch.json').exists():
            continue
        launch = load(folder / 'launch.json')
        lane = launch['lane']
        condition = {'lane': lane, 'candidate': launch['candidate'],
                     'load_ready_s': launch['load_ready_s'],
                     'engine_sha256': launch['engine_sha256'],
                     'progress': load(folder / 'progress.json') if (folder / 'progress.json').exists() else None,
                     'short': {}, 'depth_diagnostic': {}, 'long_horizon': {},
                     'long_context': {}, 'speed_probes': {}}
        grouped = {}
        for path in sorted((folder / 'short').rglob('result.json')):
            r = load(path)
            writing = r['task'].startswith('W')
            automatic = (r.get('grade') or {}).get('pass')
            row = work_unit(r, r['turns'], lane, r.get('elapsed_s'), None if writing else automatic)
            row['automatic_only_for_writing'] = writing
            if writing:
                row['automatic_format_pass'] = automatic
                answer = r.get('content', '')
                row['answer_sha256'] = hashlib.sha256(answer.encode()).hexdigest()
                review = editorial_review(reviews.get(path.relative_to(root).as_posix()), answer)
                row['editorial'] = review
                row['editorial_pass'] = review['pass'] if review else None
                row['strict_pass'] = bool(automatic and review['pass'] and not r.get('error')) if review else None
            row['result_file'] = path.relative_to(root).as_posix()
            row['unauthorized_tool_attempt'] = any(x.get('name') == 'restart_production' for x in r.get('tool_trace', []))
            row['resources'] = resources(path.parent / 'resources.jsonl')
            grouped.setdefault((r['variant'], r['task']), []).append(row)
        for (variant, task), rows in grouped.items():
            condition['short' if variant == 'main' else 'depth_diagnostic'][task] = summarize(rows)
        episodes, stages = [], {}
        for path in sorted((folder / 'long').rglob('record.json')):
            r = load(path)
            turns = [t for s in r.get('stages', []) for t in s.get('turns', [])]
            row = work_unit(r, turns, lane, r.get('elapsed_s'), r.get('complete_delivery'))
            row['result_file'] = path.relative_to(root).as_posix()
            row['final_stage_grade'] = r.get('stages', [{}])[-1].get('grade') if r.get('stages') else None
            row['stage_grades'] = [s.get('grade') for s in r.get('stages', [])]
            row['resources'] = resources(path.parent / 'resources.jsonl')
            memo = path.parent / 'workspace/delivery.md'
            row['delivery_memo_editorial'] = (editorial_review(
                reviews.get(path.relative_to(root).as_posix() + '#delivery.md'),
                memo.read_text(encoding='utf-8')) if memo.exists() else None)
            episodes.append(row)
            for s in r.get('stages', []):
                sr = {'round': r['round'], 'error': s.get('error'), 'grade': s.get('grade')}
                strict = bool((s.get('grade') or {}).get('pass') and s.get('finished_with_answer') and not s.get('error'))
                row = work_unit(sr, s.get('turns', []), lane, s.get('elapsed_s'), strict)
                row['finished_with_answer'] = s.get('finished_with_answer')
                row['stage_grade'] = s.get('grade')
                stages.setdefault(s['id'], []).append(row)
        if episodes:
            condition['long_horizon'] = {'episode': summarize(episodes),
                                          'stages': {k: summarize(v) for k, v in stages.items()}}
        grouped = {}
        for path in sorted((folder / 'context').rglob('result.json')):
            r = load(path)
            response = r.get('response') or {}
            turns = [{'timings': response.get('timings'), 'usage': response.get('usage')}]
            row = work_unit(r, turns, lane, r.get('elapsed_s'), r.get('complete_hard'))
            row.update(actual_prompt_tokens=r.get('actual_prompt_tokens'),
                       length_qualified=r.get('length_qualified'),
                       result_file=path.relative_to(root).as_posix())
            grouped.setdefault(r['task'], []).append(row)
        condition['long_context'] = {k: summarize(v) for k, v in grouped.items()}
        grouped = {}
        for path in sorted((folder / 'speed').rglob('result.json')):
            r = load(path)
            response = r.get('response') or {}
            row = work_unit(r, [{'timings': response.get('timings'), 'usage': response.get('usage')}],
                            lane, (r.get('latency') or {}).get('api_elapsed_s'), None)
            row['result_file'] = path.relative_to(root).as_posix()
            row['quality_scored'] = False
            grouped.setdefault(r['kind'], []).append(row)
        condition['speed_probes'] = {k: summarize(v) for k, v in grouped.items()}
        condition['quality_summary'] = quality_summary(condition)
        result['conditions'][folder.name] = condition
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--results', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--editorial', type=Path, help='Primary editorial reviews keyed by result_file; never auto-generated grades')
    args = parser.parse_args()
    reviews = load(args.editorial)['reviews'] if args.editorial else None
    args.output.write_text(json.dumps(analyze(args.results, reviews), ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
