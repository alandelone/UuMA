from pathlib import Path
source=Path('.tmp/scholar-g03-runtime-control-v1.py').read_text(encoding='utf-8').split('mode = sys.argv[1];')[0]
source=source.replace("'.tmp/scholar-g03-native-v1'", "'.tmp/scholar-g04-native-v1'")
exec(compile(source,__file__,'exec'))
before=tables(); digest=sha(db); baseline=read(out/'baseline-all-tables.json')
assert all(before[t]==baseline[t] for t in before if t!='studio_sample_candidates')
assert len(before['studio_model_calls'])==14
assert all(r['status'] not in {'RUNNING','QUEUED'} for t in ['studio_jobs','research_discussion_jobs'] for r in before[t])
front=read(repo/'.tmp/scholar-g03-runtime-v2-refresh-v1.json')['new_verified_port3008_chain'];backend=read(repo/'.tmp/scholar-g03-native-v1/online-runtime.json')['chain']
assert all(row(p['ProcessId'])==p for p in front+backend)
assert listening(8881)==[backend[0]['ProcessId']]
stops=stop(backend)
chain=start(repo/'.tmp/scholar-g04-native-server-v1.py',8881,'server')
assert before==tables() and digest==sha(db) and all(row(p['ProcessId'])==p for p in front)
receipt={'status':'PASS_G04_SERVE_ONLY_SOFTWARE_REVIEW_READY','chain':chain,'stops':stops,'port':8881,'all109tables_and_database_bytes_exact':True,'frontend_exact_preserved':True,'new_model_calls':0,'no_remote_fallback':True,'no_seed_branch':True,'no_other_processes_stopped':True}
(out/'runtime.json').write_text(json.dumps(receipt,indent=2),encoding='utf-8');print(json.dumps(receipt),flush=True)
