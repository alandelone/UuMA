from pathlib import Path
import hashlib,json,re,sys
sys.stdout.reconfigure(encoding='utf-8');repo=Path.cwd();out=repo/'.tmp/scholar-citation-source-resume-v1';out.mkdir()
record={}
for name in ['AGENTS.md','mission_status.json','active-session/HANDOFF.md','stage-gates/04-verification-report.md','rules/session-lifecycle.md']:
 path=repo/name;logical=path.read_text(encoding='utf-8');raw=path.read_bytes();target=out/name;target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(raw)
 record[name]={'sha256':hashlib.sha256(raw).hexdigest(),'logical_chars':len(logical)}
 if name=='active-session/HANDOFF.md':print('CURRENT_HANDOFF_HEADER\n'+logical[:9500])
 if name in {'AGENTS.md','mission_status.json','rules/session-lifecycle.md'}:print('CURRENT',name,'\n'+logical)
mission=json.loads((repo/'mission_status.json').read_text(encoding='utf-8'));assert mission['stage']=='verification' and mission['gate']['status']=='pending_review'
source_before=json.loads((repo/'.tmp/scholar-citation-source-full-v2.json').read_text(encoding='utf-8'))
current={name:hashlib.sha256((repo.parent/name).read_bytes()).hexdigest() for name in source_before['after']}
assert current==source_before['after']
record.update(previous_goal_turn='PROGRESS',current401_source_files_exact=True,original_requirement_count=118,original_group_count=11,goal_still_incomplete=True,recorded_failed_real_native_reply_preserved=True)
(out/'receipt.json').write_text(json.dumps(record,indent=2),encoding='utf-8');print(json.dumps(record),flush=True)
