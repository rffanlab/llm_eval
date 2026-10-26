"""Offline contract checks only. No endpoint, model, weight or cache operations."""
import importlib.util
import json
import sys
from pathlib import Path

from native_timing import aggregate_round, median_rounds, parse_interval, summarize

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE / 'long-horizon'))
spec = importlib.util.spec_from_file_location('paired_lh_grade', HERE / 'long-horizon/grade.py')
grader = importlib.util.module_from_spec(spec)
spec.loader.exec_module(grader)


def main():
    checks = []

    def check(name, condition):
        checks.append({'name': name, 'pass': bool(condition)})

    fault = {'tool': 'publish', 'result': {'error': 'ENOSPC_INJECTED',
             'previous_release_unchanged': True, 'published': False}}
    good = {'tool': 'publish', 'result': {'published': True}}
    for text in ['ENOSPC一次，旧版未改动，重试成功。', '磁盘空间不足后重试发布成功。',
                 '磁盘已满后再次发布成功。', '发布故障已恢复。', '发布失败，重试成功。']:
        check('recovery_wording:' + text, grader.recovery_evidence(text, [fault, good]))
    check('no_fault_ledger_rejected', not grader.recovery_evidence('ENOSPC后重试成功', [good]))
    check('no_later_publish_rejected', not grader.recovery_evidence('ENOSPC后重试成功', [fault]))
    check('publish_before_fault_is_not_recovery', not grader.recovery_evidence('ENOSPC后重试成功', [good, fault]))
    changed = {'tool': 'publish', 'result': {**fault['result'], 'previous_release_unchanged': False}}
    check('old_release_damage_rejected', not grader.recovery_evidence('ENOSPC后重试成功', [changed, good]))
    check('no_incident_description_rejected', not grader.recovery_evidence('已完成交付。', [fault, good]))

    # These deliberately differ from API completion counts. Each line is one
    # native GEN leg; a thinking close can trigger another leg in one API call.
    raw = ('maya ds4 serve: prompt 100 tokens = 40 reused + 60 read in 300 ms '
           '(200.0 tok/s), 24 generated in 6000 ms (4.00 tok/s); CPU lane 80.0% of the experts\n'
           'maya ds4 serve: prompt 130 tokens = 124 reused + 6 read in 60 ms '
           '(100.0 tok/s), 6 generated in 1000 ms (6.00 tok/s); CPU lane 80.0% of the experts\n')
    a = summarize(parse_interval(raw), complete_interval=True)
    check('all_gen_prompt_work_summed', a['new_prompt_tokens'] == 66 and a['prompt_ms'] == 360)
    check('all_gen_decode_work_summed', a['generated_tokens'] == 30 and a['decode_ms'] == 7000)
    check('cache_not_in_prefill', abs(a['prefill_tok_s'] - 66 / .36) < 1e-9)
    check('rate_uses_total_native_seconds', abs(a['decode_tok_s'] - 30 / 7) < 1e-9)
    unknown = summarize([], complete_interval=False)
    check('missing_native_unknown', unknown['prefill_tok_s'] is None and unknown['decode_tok_s'] is None)
    check('nonempty_interval_not_proof', summarize(parse_interval(raw), complete_interval=False)['decode_tok_s'] is None)
    partial = raw.replace('60 read in', '40 of 60 read in', 1)
    check('partial_prefill_not_complete', not summarize(parse_interval(partial), complete_interval=True)['capture_complete'])
    check('partial_call_blocks_whole_round_rate', aggregate_round([a, unknown])['decode_tok_s'] is None)
    b = summarize(parse_interval(raw.replace('300 ms', '600 ms')), complete_interval=True)
    total = aggregate_round([a, b])
    check('weighted_not_mean_call_prefill', abs(total['prefill_tok_s'] - 132 / 1.02) < 1e-9)
    check('missing_round_not_hidden', median_rounds([a, unknown], 'decode_tok_s') is None)
    zero = summarize(parse_interval(raw.splitlines()[0].replace('60 read in 300 ms', '0 read in 0 ms')), complete_interval=True)
    check('zero_new_input_rate_unknown', zero['prefill_tok_s'] is None)

    # Exercise the actual inherited pure-function and artifact oracle, not a
    # source-text mirror. No model-generated code is executed by this check.
    source = (HERE / 'long-horizon/reference.py').read_text(encoding='utf-8')
    for stage in (1, 2, 3, 4):
        result = grader.suite(source, stage)
        check('reference_stage_' + str(stage), result['pass'])
    from fixture import expected
    env = grader.load(source)
    for dataset in ('base', 'v2', 'final'):
        check('reference_bundle_' + dataset,
              grader.bundle_grade(env['export_bundle'](expected(dataset)), expected(dataset))['pass'])
    result = {'scope': 'offline_harness_only_not_model_validation',
              'checks': checks, 'pass': all(row['pass'] for row in checks),
              'model_requests': 0, 'protocol_frozen': False}
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result['pass'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
