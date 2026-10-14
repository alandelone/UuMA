from pathlib import Path
import hashlib
import json
import re
r=Path.cwd()
review=r/'docs/reviews/scholar-rstv4-2026-09-30'
text=(review/'ui-requirements-preservation.md').read_text(encoding='utf-8')
rows=[line for line in text.splitlines() if re.match(r'^\|\s*(OV|CA|RV|AC|KG|TR|ST|WF|RE|CH)-\d+',line)]
print('ORIGINAL_REQUIREMENT_ROWS',len(rows))
print('TARGET_ROWS',[line for line in rows if any(i in line for i in ['ST-19','ST-16','ST-28','WF-03','WF-06','RE-14'])])
print('ORIGINAL_GROUP_LINES',[line for line in text.splitlines() if re.search(r'G-?0?[1-9]|G-?1[01]',line)][-20:])
for name in ['formal-download-retry-2026-10-09','formal-intent-correspondence-2026-10-09']:
    root=review/name
    manifest=json.loads((root/'manifest.json').read_text(encoding='utf-8'))
    records=manifest['files']
    assert isinstance(records,dict)
    for filename,record in records.items():
        sha=record if isinstance(record,str) else record['sha256']
        assert hashlib.sha256((root/filename).read_bytes()).hexdigest()==sha,filename
    print('PARENT_SEALED_FILES_EXACT',name,len(records))
full=json.loads((r/'.tmp/scholar-generated-assets-full-v2.json').read_text(encoding='utf-8'))
assert full['status']=='PASS' and full['before_sha256']==full['after_sha256'] and not full['changed_during_verification']
for filename,sha in full['after_sha256'].items():assert hashlib.sha256(Path(filename).read_bytes()).hexdigest()==sha,filename
assert '1051 passed, 20 warnings' in (r/'.tmp/scholar-generated-assets-full-v2.log').read_text(encoding='utf-8')
assert '67 passed' in (r/'.tmp/scholar-generated-assets-focused-v9.log').read_text(encoding='utf-8')
static=json.loads((r/'.tmp/scholar-generated-assets-static-v2.json').read_text(encoding='utf-8'))
assert len(full['results'])==23 and len(static)==15 and all(v['exit_code']==0 for v in full['results']+static)
print('FINAL_VALIDATION',1051,67,23,15,'STABLE_SOURCE_FILES',len(full['after_sha256']))
receipt=json.loads((r/'.tmp/scholar-generated-assets-native-audit-v3/receipt.json').read_text(encoding='utf-8'))
print('FINAL_NATIVE', {key:receipt[key] for key in ['manuscript_id','generated_version_id','author_revision','declared_fixture_model_calls','package_id','pdf_sha256','zip_sha256','zip_files','zip_bytes']})
