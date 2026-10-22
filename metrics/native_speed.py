"""Native throughput for one work unit, using token/time sums, never wall time."""
import math
import statistics


def number(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def aggregate_turns(turns):
    turns = list(turns)
    result = {'calls_total': len(turns)}
    for label, token_key, time_key in [('prefill', 'prompt_n', 'prompt_ms'),
                                       ('decode', 'predicted_n', 'predicted_ms')]:
        valid = []
        zero_work = 0
        for turn in turns:
            t = turn.get('timings') or {}
            n, ms = t.get(token_key), t.get(time_key)
            # A full cache hit can legitimately report zero new tokens and
            # zero compute time. It contributes no work, rather than missing
            # timing, to a multi-call aggregate. Its standalone rate is undefined.
            if number(n) and number(ms) and n == 0 and ms == 0:
                valid.append((n, ms))
                zero_work += 1
            elif number(n) and number(ms) and n >= 0 and ms > 0:
                valid.append((n, ms))
        n = sum(x[0] for x in valid)
        ms = sum(x[1] for x in valid)
        complete = bool(turns) and len(valid) == len(turns)
        result.update({label+'_calls_measured': len(valid), label+'_timing_complete': complete,
                       label+'_zero_work_calls': zero_work,
                       label+'_tokens_measured': n, label+'_ms_measured': ms,
                       label+'_tokens_s': n*1000/ms if complete and n > 0 and ms > 0 else None})
    caches = [(t.get('timings') or {}).get('cache_n') for t in turns]
    result['cached_tokens'] = sum(caches) if all(number(x) and x >= 0 for x in caches) else None
    return result


def summarize_rounds(rounds):
    out = {'round_count': len(rounds)}
    for name in ['prefill', 'decode']:
        values = [x['native_speed'][name+'_tokens_s'] for x in rounds]
        known = [x for x in values if number(x)]
        out[name+'_rounds_measured'] = len(known)
        out[name+'_median_tokens_s'] = statistics.median(known) if known and len(known) == len(values) else None
    return out
