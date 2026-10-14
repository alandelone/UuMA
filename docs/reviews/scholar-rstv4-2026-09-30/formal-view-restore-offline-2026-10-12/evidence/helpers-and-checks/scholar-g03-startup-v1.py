from pathlib import Path
import hashlib,json,sys,re
sys.stdout.reconfigure(encoding='utf-8');repo=Path.cwd();out=repo/'.tmp/scholar-g03-startup-v1';out.mkdir();sha=lambda p:hashlib.sha256(Path(p).read_bytes()).hexdigest()
mission=json.loads((repo/'mission_status.json').read_text(encoding='utf-8'));assert mission['stage']=='verification' and mission['gate']['status']=='pending_review'
reads={}
for name in ['AGENTS.md','mission_status.json','rules/session-lifecycle.md',mission['gate']['current'],'active-session/HANDOFF.md']:
    p=repo/name;raw=p.read_bytes();logical=p.read_text(encoding='utf-8');dst=out/name;dst.parent.mkdir(parents=True,exist_ok=True);dst.write_bytes(raw)
    reads[name]={'sha256':sha(p),'logical_chars':len(logical)}
    if name in ['AGENTS.md','rules/session-lifecycle.md']:print(logical)
    if name=='active-session/HANDOFF.md':print('FRESH SHARED HANDOFF PREFIX\n'+logical[:15000])
seal=json.loads((repo/'.tmp/scholar-g02-seal-v1.json').read_text(encoding='utf-8'));report=Path(seal['directory']);manifest=json.loads((report/'manifest.json').read_text(encoding='utf-8'))
assert len(manifest['files'])==109 and all(sha(report/p)==digest for p,digest in manifest['files'].items())
assert all(sha(p)==digest for p,digest in manifest['current_source_sha256'].items())
scope=(repo/'docs/reviews/scholar-rstv4-2026-09-30/ui-requirements-preservation.md').read_text(encoding='utf-8');rows=[x for x in scope.splitlines() if re.match(r'^\|\s*(OV|CA|RV|AC|KG|TR|ST|WF|RE|CH)-\d+',x)];groups=[x for x in scope.splitlines() if re.match(r'^\|\s*G-\d+',x)];assert len(rows)==118 and len(groups)==11
receipt={'previous_goal_turn':'PROGRESS','full_startup_reads':reads,'previous109_sealed_files_exact':True,'previous12_source_files_current_exact':True,'original_requirements':118,'original_groups':11,'g03_definition':groups[2],'all11_complete':False,'sibling_index_and_instructions':{p:Path(p).exists() for p in ['../RSTV4/.codegraph','../writing-studio/.codegraph','../RSTV4/AGENTS.md','../writing-studio/AGENTS.md']}}
(out/'receipt.json').write_text(json.dumps(receipt,ensure_ascii=False,indent=2),encoding='utf-8');print(json.dumps(receipt,ensure_ascii=False),flush=True)
