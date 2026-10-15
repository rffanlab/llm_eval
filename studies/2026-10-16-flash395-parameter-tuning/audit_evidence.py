"""Offline additive audit; does not modify frozen inputs, model outputs or grades."""
import pathlib,json,hashlib,collections,datetime
S=pathlib.Path(__file__).resolve().parent
def read(p):return json.loads(p.read_bytes())
def main():
 summary=read(S/'summary.json');assert summary['results_complete'] and summary['frozen_sources_unchanged']
 env=read(S/'environments.json');rows=[];boot_ids=set();times=[]
 for phase in ['screen','calibrate','validate']:
  for kind,filename in [('speed','result.json'),('short','result.json'),('long','record.json')]:
   for path in sorted((S/'results'/phase/kind).rglob(filename)):
    d=read(path);profile=d['profile'];base=path.parent
    expected=[base/'admission.json'] if kind=='speed' else [base/f'admission-{i+1}.json' for i in range(len(d['turns']))] if kind=='short' else [base/'admission'/f'{sid}-{i+1}.json' for sid,stage in enumerate(d['stages'],1) for i in range(len(stage['turns']))]
    assert expected,'empty case has no API admission'
    admissions=[]
    for p in expected:
     a=read(p);proc=a['processes'];mem=a['resource']['MemAvailable'];boot_ids.add(a['boot_id'])
     assert a['profile']==profile and len(proc)==2 and all(x['registered'] for x in proc)
     assert sorted(x['name'] for x in proc)==['python','strata']
     assert mem>=12*2**30 and a['activity']['in_flight']==0
     assert a['config_without_key_sha256']==env[profile]['config_without_key_sha256']
     admissions.append({'source':p.relative_to(S).as_posix(),'sha256':hashlib.sha256(p.read_bytes()).hexdigest(),'MemAvailable_bytes':mem})
    rows.append({'phase':phase,'kind':kind,'profile':profile,'source':path.relative_to(S).as_posix(),'admissions':admissions})
    if isinstance(d.get('started_at_epoch'),(int,float)):times.append(d['started_at_epoch'])
 counts=dict(collections.Counter(x['kind'] for x in rows));phases=dict(collections.Counter(x['phase'] for x in rows))
 assert len(rows)==60 and counts=={'speed':16,'short':40,'long':4} and phases=={'screen':16,'calibrate':12,'validate':32},(len(rows),counts,phases)
 assert len(boot_ids)==1,'boot changed; review retained logs before attributing stability'
 audit={'audit_pass':True,'case_count':len(rows),'kind_counts':counts,'phase_counts':phases,'admission_count':sum(len(x['admissions']) for x in rows),'boot_count':len(boot_ids),'definition':'Each observed API call has a prior idle, single-model, sealed-config admission with MemAvailable>=12GiB. Resource peaks use separate sampled evidence.','cases':rows}
 (S/'admission-audit.json').write_bytes((json.dumps(audit,ensure_ascii=False,indent=2)+'\n').encode())
 files={p.relative_to(S).as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted((S/'results').rglob('*')) if p.is_file() and p.name!='.gitattributes'}
 dest=S/'raw-manifest.json'
 if dest.exists():assert read(dest)['files']==files,'never silently rebaseline a sealed raw manifest'
 else:dest.write_bytes((json.dumps({'definition':'All raw results including separately labelled unscored warmups; never substitutes for frozen acceptance.','files':files},indent=2)+'\n').encode())
 tz=datetime.timezone(datetime.timedelta(hours=8));dates=sorted({datetime.datetime.fromtimestamp(t,tz).date().isoformat() for t in times})
 window={'timezone':'Asia/Shanghai','first_measured_start_epoch':min(times),'last_measured_start_epoch':max(times),'measured_start_dates':dates,'display_dates':' 至 '.join(dates) if len(dates)>1 else dates[0]}
 (S/'run-window.json').write_bytes((json.dumps(window,ensure_ascii=False,indent=2)+'\n').encode())
 print(json.dumps({'formal_cases':len(rows),'admissions':audit['admission_count'],'raw_files':len(files),'dates':dates}))
if __name__=='__main__':main()
