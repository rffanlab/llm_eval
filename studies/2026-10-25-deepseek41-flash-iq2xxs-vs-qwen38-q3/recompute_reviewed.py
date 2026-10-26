"""Verify public evidence and recompute all reported per-unit native/API metrics.

No network, model requests, generated-code execution, or changes to frozen scores.
"""
from pathlib import Path
import argparse,hashlib,json,re,statistics
R=Path(__file__).resolve().parent
def load(p):return json.loads(p.read_text(encoding='utf-8'))
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def kb(text,label):return int(next(l.split()[1] for l in text.splitlines() if l.startswith(label+':')))
def med(xs):return statistics.median(xs) if all(x is not None for x in xs) else None
def native(calls):
    legs=[l for c in calls for l in c['timing'].get('native_capture',{}).get('all_GEN_legs',[])]
    closed=bool(calls) and all(c['timing'].get('SSE_DONE_seen') and not c['timing'].get('error') and c['timing'].get('native_capture',{}).get('capture_complete') for c in calls)
    if not closed:return dict(complete=False,prefill_tok_s=None,decode_tok_s=None,all_legs_observed=legs,closed_calls=sum(bool(c['timing'].get('SSE_DONE_seen') and not c['timing'].get('error') and c['timing'].get('native_capture',{}).get('capture_complete')) for c in calls),total_calls=len(calls))
    t={a:sum(x[b] for x in legs) for a,b in [('new_prompt_tokens','read'),('generated_tokens','generated'),('prompt_ms','prompt_ms'),('decode_ms','decode_ms')]}
    return dict(complete=True,**t,prefill_tok_s=t['new_prompt_tokens']*1000/t['prompt_ms'],decode_tok_s=t['generated_tokens']*1000/t['decode_ms'],GEN_legs=len(legs),calls=len(calls))
def verify():
    freeze=load(R/'freeze.json');assert sha(R/'freeze.json')=='9b248df4befdafc2c3f75c0f9565422d2de5df7a0e407321da935c0a3d51c31e'
    assert all(sha(R/n)==h for n,h in freeze['files'].items())
    manifest=load(R/'result-file-manifest.json')['files']
    for n,m in manifest.items():assert sha(R/'results'/n)==m['public_SHA256'] and (R/'results'/n).stat().st_size==m['public_bytes']
    expected=load(R/'metrics-reviewed.json');reviews=load(R/'editorial-reviewed.json');index=load(R/'public-units.json');seen=set();units=0;partial=0;stages=0
    for family,report in expected['families'].items():
        for u in report['units']:
            key=family+'/'+u['id'];root=R/'results'/key;result=load(root/index[key]['result_file']);review=reviews[key];calls=[load(p) for p in sorted(root.rglob('*.evidence.json'))];assert len(calls)
            assert index[key]['original_result_SHA256']==u['raw_result_SHA256']==review['original_result_SHA256']
            assert u['primary_receipt_SHA256']==review['original_primary_receipt_SHA256']
            assert u['fixed_grade']==result.get('grade')
            actual=native(calls);assert actual==u['native'],key
            for p in sorted(root.rglob('*.evidence.json')):
                c=load(p);t=c['timing'];cap=t['native_capture'];native_log=p.with_name(p.name.replace('.evidence.json','.native.log')).read_text()
                for leg in cap['all_GEN_legs']:assert leg['raw'] in native_log and leg['prompt']==leg['cache']+leg['read']
                if t['SSE_DONE_seen'] and not t['error'] and cap['capture_complete']:
                    m=cap['metrics_new_request'];assert m['id'] not in seen;seen.add(m['id']);legs=cap['all_GEN_legs']
                    assert sum(l['generated'] for l in legs)==m['engine_generated']
                    assert abs(sum(l['prompt_ms'] for l in legs)-m['prompt_ms'])<=len(legs)+.1
                    assert abs(sum(l['decode_ms'] for l in legs)-m['decode_ms'])<=len(legs)+.1
                else:partial+=1
            usages=[c['response']['usage'] for c in calls if c['timing']['SSE_DONE_seen'] and not c['timing']['error']]
            api={'closed_calls':len(usages),'all_calls':len(calls),'complete':actual['complete'],'input_sum':sum(x['prompt_tokens'] for x in usages) if actual['complete'] else None,'output_sum':sum(x['completion_tokens'] for x in usages) if actual['complete'] else None,'cache_sum':sum(x.get('prompt_tokens_details',{}).get('cached_tokens',0) for x in usages) if actual['complete'] else None,'wait_s':sum(c['timing']['api_elapsed_s'] for c in calls)}
            assert api==u['API']
            strict=review['strict_pass'] if review['strict_pass'] is not None else result.get('complete_hard',result.get('complete_delivery'))
            if u['category']=='short' and 'depth' not in u['id'] and not actual['complete']:strict=False
            assert strict==u['strict_pass']
            assert review['editorial_of20']==u['editorial_of20']
            if 'elapsed_s' in result:assert result['elapsed_s']==u['complete_wait_s']
            else:assert u['parent_wait_s']==u['complete_wait_s']
            assert [c['timing']['first_content_s'] for c in calls]==u['first_content_s']
            samples=[json.loads(l) for p in root.rglob('resources.jsonl') for l in p.read_text().splitlines()]
            assert all(kb(x['memory'],'HardwareCorrupted')==4 for x in samples)
            rs=u['resources'];assert len(samples)==rs['samples']
            assert min(kb(x['memory'],'MemAvailable') for x in samples)==rs['system_MemAvailable_min_kB']
            rss=[kb(x['host_process_status'],'VmRSS') for x in samples if x.get('host_process_status') and 'VmRSS:' in x['host_process_status']]
            assert max(rss)==rs['main_host_process_VmRSS_peak_kB']
            assert max(int(v) for x in samples for k,v in x['GPU'].items() if k.endswith('/mem_info_vram_used'))==rs['VRAM_used_peak_bytes']
            assert max(int(v) for x in samples for k,v in x['GPU'].items() if k.endswith('/mem_info_gtt_used'))==rs['GTT_used_peak_bytes']
            if u['id'].startswith('LH'):
                for a,b in zip(u['stages'],result['stages'],strict=True):
                    assert a['native']==native([{'timing':t} for t in b['turns']]);assert a['functional_grade']==b.get('grade');assert a['complete_wait_s']==b.get('elapsed_s');assert a['finished_with_answer']==b['finished_with_answer'];assert a['calls']==len(b['turns']);stages+=1
                assert u['delivery_editorial_of20']==review['delivery_editorial_of20'];assert u['delivery_fact_veto']==review['delivery_fact_veto']
            if u['id'].startswith('LC'):
                assert u['actual_API_input']==result['actual_prompt_tokens']==api['input_sum'];assert u['length_qualified']==result['length_qualified'];assert u['prompt_bytes']==result['prompt_bytes'];assert u['prompt_SHA256']==result['prompt_sha256']
            units+=1
        for task,summary in report['by_task'].items():
            rows=[u for u in report['units'] if u['id'] in [task+'-r1',task+'-r2']];assert len(rows)==2
            assert summary['strict_passes']==sum(bool(u['strict_pass']) for u in rows)
            for output,field in [('complete_wait_median_s','complete_wait_s')]:assert summary[output]==med([u[field] for u in rows])
            for output,field in [('prefill_median_tok_s','prefill_tok_s'),('decode_median_tok_s','decode_tok_s')]:assert summary[output]==med([u['native'][field] for u in rows])
            for output,field in [('API_input_rounds','input_sum'),('API_output_rounds','output_sum'),('API_cache_rounds','cache_sum')]:assert summary[output]==[u['API'][field] for u in rows]
            assert summary['editorial_of20_rounds']==[u['editorial_of20'] for u in rows];assert summary['functional_scores']==[u['fixed_grade'].get('score') for u in rows]
        for kind,summary in report['speed_probes'].items():
            rows=[u for u in report['units'] if u['id'].startswith(kind+'-')];assert len(rows)==3
            assert summary['prefill_median_tok_s']==med([u['native']['prefill_tok_s'] for u in rows]);assert summary['decode_median_tok_s']==med([u['native']['decode_tok_s'] for u in rows]);assert summary['complete_wait_median_s']==med([u['complete_wait_s'] for u in rows]);assert summary['actual_input_rounds']==[u['API']['input_sum'] for u in rows];assert summary['API_cache_rounds']==[u['API']['cache_sum'] for u in rows]
        for prefix,name,waitkey in [('LC','LC','full_wait_median_s'),('LH','LH','complete_wait_median_s')]:
            rows=[u for u in report['units'] if u['id'].startswith(prefix)];assert len(rows)==2
            assert report[name][waitkey]==med([u['complete_wait_s'] for u in rows]);assert report[name]['prefill_median_tok_s']==med([u['native']['prefill_tok_s'] for u in rows]);assert report[name]['decode_median_tok_s']==med([u['native']['decode_tok_s'] for u in rows])
        assert report['sum_attempt_wait_s']==sum(u['complete_wait_s'] for u in report['units'])
    q=expected['families']['qwen'];assert q['quality_total_100']==30+25*statistics.mean(u['fixed_grade']['score'] for u in q['units'] if u['id'].startswith(('A01','A02')))/100+statistics.mean(u['editorial_of20'] for u in q['units'] if u['id'].startswith(('W01','W03')))+10+15==92.375
    assert expected['families']['dsv41']['quality_total_100'] is None
    assert units==58 and len(seen)==165 and partial==6
    return {'units':units,'public_files_SHA_verified':len(manifest),'all_unit_and_stage_native_API_and_resource_fields_match':True,'stages_observed':stages,'closed_unique_metrics':len(seen),'partial_calls':partial,'freeze_files_unchanged':len(freeze['files']),'no_inference':True}
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--output',type=Path);a=p.parse_args();z=verify()
    if a.output:a.output.write_text(json.dumps(z,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(z,ensure_ascii=False))
