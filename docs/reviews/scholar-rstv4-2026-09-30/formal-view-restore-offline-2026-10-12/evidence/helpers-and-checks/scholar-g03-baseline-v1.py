from pathlib import Path
import hashlib,json,sqlite3,subprocess,sys
sys.stdout.reconfigure(encoding='utf-8');repo=Path.cwd();out=repo/'.tmp/scholar-g03-native-v1';out.mkdir();read=lambda p:json.loads(Path(p).read_text(encoding='utf-8'))
fixture=read(repo/'.tmp/scholar-citation-source-native-v1.json');db=Path(fixture['root'])/'data/catalog.db';raw=hashlib.sha256(db.read_bytes()).hexdigest()
with sqlite3.connect(f'file:{db.as_posix()}?mode=ro',uri=True) as conn:
    conn.row_factory=sqlite3.Row;conn.execute('PRAGMA query_only=ON');tables={r[0]:[dict(x) for x in conn.execute(f'SELECT * FROM "{r[0]}" ORDER BY rowid')] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")}
previous=read(repo/'.tmp/scholar-g02-typed-native-v1/reopened-final/all-tables.json')
assert len(tables)==109 and all(tables[t]==previous[t] for t in tables if t!='studio_sample_candidates')
assert len(tables['manuscripts'])==1 and tables['studio_documents'][0]['revision']==13 and len(tables['studio_model_calls'])==14
front=read(repo/'.tmp/scholar-g02-source-runtime-refresh-v1.json')['new_verified_port3008_chain'];back=read(repo/'.tmp/scholar-g02-typed-native-v1/runtime.json')['new_verified_port8881_chain']
ids=[p['ProcessId'] for p in front+back];command="Get-CimInstance Win32_Process -Filter '"+' OR '.join('ProcessId='+str(p) for p in ids)+"' | Select-Object ProcessId,ParentProcessId,CommandLine,CreationDate | ConvertTo-Json"
fresh=json.loads(subprocess.check_output(['powershell','-NoProfile','-Command',command],encoding='utf-8-sig'));assert len(fresh)==6 and all(row==next(p for p in fresh if p['ProcessId']==row['ProcessId']) for row in front+back)
ports=json.loads(subprocess.check_output(['powershell','-NoProfile','-Command','Get-NetTCPConnection -State Listen | Select-Object LocalPort,OwningProcess | ConvertTo-Json'],encoding='utf-8-sig'))
assert any(p['LocalPort']==3008 and p['OwningProcess']==114008 for p in ports) and any(p['LocalPort']==8881 and p['OwningProcess']==114708 for p in ports)
assert not any(p['LocalPort'] in [3000,3004,3005,3006,3007] for p in ports)
(out/'baseline-all-tables.json').write_text(json.dumps(tables,ensure_ascii=False,indent=2),encoding='utf-8');assert hashlib.sha256(db.read_bytes()).hexdigest()==raw
receipt={'status':'PASS_CURRENT_G03_BASELINE','root':fixture['root'],'manuscript_a':fixture['manuscript_id'],'author_revision':13,'all_old_protected_records_exact':True,'new_model_calls':0,'verified_current_frontend':front,'verified_current_backend':back,'read_only_database_bytes_preserved':True}
(out/'baseline.json').write_text(json.dumps(receipt,indent=2),encoding='utf-8');print(json.dumps(receipt),flush=True)
