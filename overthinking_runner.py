"""Run one registered short thinking comparison against an OpenAI-compatible API.

Set LOCAL_BASE_URL, LOCAL_API_KEY and LOCAL_MODEL without saving credentials.
Preserve each first attempt, including timeouts and API failures.
"""
import argparse
import datetime
import hashlib
import json
import os
from pathlib import Path
import time
import urllib.request


def run(study, profile, task, mode, round_, suite_name='overthinking-tasks.json', collection='overthinking', reasoning_effort=None, preserve_thinking=None):
    study = Path(study)
    raw = (study / suite_name).read_bytes()
    suite = json.loads(raw)
    case = next(c for c in suite['cases'] if c['id'] == task)
    assert mode in ['on', 'off'] and round_ in [1, 2]
    target = study / collection / profile / f'{task}-{mode}-r{round_}.json'
    if target.exists():
        raise SystemExit('preserve existing attempt')
    payload = {'model': os.environ['LOCAL_MODEL'],
               'messages': [{'role': 'system', 'content': suite['system']},
                            {'role': 'user', 'content': case['prompt']}],
               'temperature': 0, 'enable_thinking': mode == 'on',
               'max_tokens': suite['max_tokens'], 'stream': False}
    if reasoning_effort:payload['reasoning_effort']=reasoning_effort if mode=='on' else 'none'
    if preserve_thinking is not None:payload['chat_template_kwargs']={'enable_thinking':mode=='on','reasoning_effort':reasoning_effort if mode=='on' else 'none','preserve_thinking':preserve_thinking}
    record = {'profile': profile, 'task': task, 'thinking': mode, 'round': round_,
              'fixture_sha256': hashlib.sha256(raw).hexdigest(),
              'started_at': datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=8))).isoformat(),
              'payload': payload}
    at = time.monotonic()
    try:
        request = urllib.request.Request(
            os.environ['LOCAL_BASE_URL'].rstrip('/') + '/chat/completions',
            data=json.dumps(payload, ensure_ascii=False).encode(),
            headers={'Content-Type': 'application/json',
                     'Authorization': 'Bearer ' + os.environ['LOCAL_API_KEY']})
        with urllib.request.urlopen(request, timeout=90) as response:
            data = json.load(response)
        record['response'] = data
        content = data['choices'][0]['message'].get('content') or ''
        if 'expected_text' in case:
            passed = content.strip() == case['expected_text']
        else:
            try:
                value = json.loads(content)
                expected = case['expected_json']
                passed = (isinstance(value, dict) and set(value) == set(expected)
                          and all(type(value[k]) is type(v) and value[k] == v
                                  for k, v in expected.items()))
            except (ValueError, TypeError, KeyError):
                passed = False
        record['pass'] = passed
    except Exception as exc:
        record.update(error=type(exc).__name__, **{'pass': False})
    record['elapsed_s'] = time.monotonic() - at
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(record, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print('THINKING_CASE', profile, task, mode, round_, record['pass'],
          round(record['elapsed_s'], 3), record.get('response', {}).get('usage'), flush=True)
    return record


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--study', type=Path, required=True)
    parser.add_argument('--profile', required=True)
    parser.add_argument('--task', choices=['O01', 'O02', 'O03'], required=True)
    parser.add_argument('--thinking', choices=['on', 'off'], required=True)
    parser.add_argument('--round', type=int, choices=[1, 2], required=True)
    parser.add_argument('--native',action='store_true',help='registered 4096-budget supplement, separate collection')
    parser.add_argument('--reasoning-effort',choices=['medium'])
    args = parser.parse_args()
    run(args.study,args.profile,args.task,args.thinking,args.round,
        'overthinking-native-tasks.json' if args.native else 'overthinking-tasks.json',
        'overthinking-native' if args.native else 'overthinking',args.reasoning_effort)
