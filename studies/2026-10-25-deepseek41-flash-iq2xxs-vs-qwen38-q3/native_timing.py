"""Read native per-GEN stderr summaries; never infer timing from API wall time.

Caller supplies only the exact engine-log byte interval for one serial API call.
API usage and matching /metrics records must be saved separately. Preflight must
validate interval completeness before formal use; parsing does not prove it.
"""
import math
import re
import statistics


REQUEST = re.compile(
    r"prompt (?P<prompt>\d+) tokens = (?P<cache>\d+) reused \+ "
    r"(?P<read>\d+)(?: of (?P<expected_read>\d+))? read in "
    r"(?P<prompt_ms>\d+(?:\.\d+)?) ms \([\d.]+ tok/s\), "
    r"(?P<generated>\d+) generated in (?P<decode_ms>\d+(?:\.\d+)?) ms "
    r"\([\d.]+ tok/s\)"
)


def parse_interval(text):
    """Native log precision is retained, including genuine zero observations."""
    rows = []
    for line_no, line in enumerate(text.splitlines(), 1):
        match = REQUEST.search(line)
        if match is None:
            continue
        fields = match.groupdict()
        row = {k: int(fields[k]) for k in ('prompt', 'cache', 'read', 'generated')}
        row.update({k: float(fields[k]) for k in ('prompt_ms', 'decode_ms')})
        row['expected_read'] = int(fields['expected_read']) if fields['expected_read'] else row['read']
        row.update(line_no=line_no, raw=line,
                   prompt_complete=row['read'] == row['expected_read'])
        rows.append(row)
    return rows


def _rate(tokens, milliseconds):
    if tokens is None or milliseconds is None or tokens == 0 or milliseconds <= 0:
        return None
    return tokens / (milliseconds / 1000)


def summarize(rows, *, complete_interval):
    """Sum all GEN legs, including thinking-wrap continuations.

    complete_interval is an independently established capture property, never
    guessed from a nonempty log or a successful HTTP return.
    """
    fields = ('read', 'prompt_ms', 'generated', 'decode_ms')
    valid = bool(rows) and all(
        isinstance(row.get(k), (int, float)) and not isinstance(row.get(k), bool)
        and math.isfinite(row[k]) and row[k] >= 0
        for row in rows for k in fields
    )
    complete = bool(complete_interval and valid and all(row.get('prompt_complete') for row in rows))
    totals = {k: sum(row[k] for row in rows) if valid else None for k in fields}
    return {
        'native_legs': len(rows), 'capture_complete': complete,
        'new_prompt_tokens': totals['read'], 'prompt_ms': totals['prompt_ms'],
        'generated_tokens': totals['generated'], 'decode_ms': totals['decode_ms'],
        'prefill_tok_s': _rate(totals['read'], totals['prompt_ms']) if complete else None,
        'decode_tok_s': _rate(totals['generated'], totals['decode_ms']) if complete else None,
        'timing_source': 'native_engine_stderr_summaries',
        'precision_note': 'Use the native milliseconds as printed; do not reconstruct higher precision from displayed tok/s.',
    }


def aggregate_round(calls):
    """No partial-call rate can masquerade as the whole task's native speed."""
    complete = bool(calls) and all(call.get('capture_complete') for call in calls)
    mapping = {'new_prompt_tokens': 'read', 'prompt_ms': 'prompt_ms',
               'generated_tokens': 'generated', 'decode_ms': 'decode_ms'}
    totals = {
        field: sum(call[field] for call in calls) if complete else None
        for field in mapping
    }
    return {**totals, 'calls': len(calls),
            'complete_native_calls': sum(bool(c.get('capture_complete')) for c in calls),
            'capture_complete': complete,
            'prefill_tok_s': _rate(totals['new_prompt_tokens'], totals['prompt_ms']),
            'decode_tok_s': _rate(totals['generated_tokens'], totals['decode_ms'])}


def median_rounds(rounds, field):
    """Missing rounds stay unknown; callers may show valid individual rounds."""
    values = [row.get(field) for row in rounds]
    if not values or any(value is None for value in values):
        return None
    return statistics.median(values)
