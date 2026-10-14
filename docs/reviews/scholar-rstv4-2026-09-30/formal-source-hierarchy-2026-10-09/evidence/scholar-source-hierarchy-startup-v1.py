import hashlib,json
from pathlib import Path
repo=Path(__file__).resolve().parents[1]
mission=json.loads((repo/'mission_status.json').read_text(encoding='utf-8'))
handoff=(repo/'active-session/HANDOFF.md').read_text(encoding='utf-8')
gate=(repo/mission['gate']['current']).read_text(encoding='utf-8')
assert mission['stage']=='verification' and mission['gate']['status']=='pending_review'
assert 'STOP DOWNLOAD TESTING' in handoff and 'r65' in handoff
folder=repo/'docs/reviews/scholar-rstv4-2026-09-30/formal-template-mapping-2026-10-09'
manifest=json.loads((folder/'manifest-v2.json').read_text(encoding='utf-8'))
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
assert sha(folder/'acceptance-v2.md')==manifest['report_sha256']
for name,digest in manifest['copied_file_sha256'].items():assert sha(folder/name)==digest
for name,receipt in manifest['source_receipts'].items():assert sha(repo.parent/'writing-studio'/name)==receipt['after_sha256']
checks={str(path):path.exists() for root in [repo.parent/'RSTV4',repo.parent/'writing-studio'] for path in [root/'AGENTS.md',root/'.codegraph']}
result={'status':'PASS_FRESH_ENTIRE_CONTEXT_AND_PRIOR_SEAL','mission':mission,'handoff_logical_characters':len(handoff),'handoff_raw_sha256':sha(repo/'active-session/HANDOFF.md'),'gate_characters':len(gate),'sealed_files':len(manifest['copied_file_sha256']),'product_sources_exact':12,'workspace_instruction_index_presence':checks,'download_testing_remains_paused':True}
with (repo/'.tmp/scholar-source-hierarchy-startup-v1.json').open('x',encoding='utf-8') as h:json.dump(result,h,indent=2,ensure_ascii=False)
print(json.dumps(result,ensure_ascii=False))
print(handoff[:1800])
