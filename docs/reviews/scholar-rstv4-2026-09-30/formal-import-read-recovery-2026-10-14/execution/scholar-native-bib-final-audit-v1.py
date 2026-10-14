from pathlib import Path
import hashlib
import json
import sys
repo=Path(__file__).resolve().parents[1]
here=repo/'.tmp/scholar-native-import-v1'
sys.path.insert(0,str(repo/'.tmp/scholar-g11-parallel-v1'))
from runtime_copy_and_serve_v6 import snapshot, product_guard
product_guard()
copy=json.loads((here/'copy-receipt.json').read_text())
actual=json.loads(json.dumps(snapshot(Path(copy['root'])/'data/catalog.db')))
before=json.loads((here/'after-four-native-imports-all-tables.json').read_text())
assert actual==before
original=json.loads((here/'protected-original-files.json').read_text())
source=Path(copy['source'])
observed={p.relative_to(source).as_posix():{'bytes':p.stat().st_size,'sha256':hashlib.sha256(p.read_bytes()).hexdigest()} for p in source.rglob('*') if p.is_file() and not p.name.endswith(('-wal','-shm'))}
assert observed==original
bib=here/'bib-native-v1'
ready=json.loads((bib/'ready.json').read_text())
assert ready['oversize']['bytes']==5000001
assert Path(ready['oversize']['path']).stat().st_size==5000001
assert hashlib.sha256(Path(ready['bib']['path']).read_bytes()).hexdigest()==ready['bib']['sha256']
normal=json.loads((bib/'01-local-file-ready.json').read_text())
over=json.loads((bib/'02-over-limit-preserved.json').read_text())
checked=json.loads((bib/'03-checked-no-task.json').read_text())
assert normal['value']==over['value']==checked['value']==ready['bib']['text'].replace('\r\n','\n')
assert normal['status']=='PASS_NATIVE_LOCAL_BIB_TEXT_READ'
assert over['status']=='PASS_NATIVE_5000001_BYTE_REJECTED_INPUT_RETAINED'
assert checked['status']=='PASS_NATIVE_BIB_INPUT_CHECK_ONLY' and checked['collectionStarted'] is False
assert all(r['method'] in {'GET','HEAD','OPTIONS'} for r in normal['requests'])
posts=[r for r in checked['requests'] if r['method']=='POST']
assert len(posts)==1 and posts[0]['url']=='http://127.0.0.1:8891/api/catalog/collections/preview'
body=json.loads(posts[0]['postData'])
assert body['bibtex']==normal['value']
assert 'form-data' not in str(posts[0]['headers']).lower()
assert '检查通过；已有 1 篇，可复用 1 份 PDF，待审核 0 篇。尚未创建任务。' in (bib/'03-checked-no-task.dom.txt').read_text(encoding='utf-8')
out={'status':'PASS_NATIVE_BIB_LOCAL_READ_SIZE_LIMIT_PREVIEW_SUBSET','all_109_tables_schema_and_rows_exact':True,'original_source_files_exact':True,'real_file_chooser_used':True,'bib_sha256':ready['bib']['sha256'],'oversize_bytes':5000001,'local_file_not_uploaded':True,'input_retained_after_oversize':True,'preview_json_post_only':True,'new_collections_jobs_models':0,'slow_read_race_verified':False,'ac03_complete':False,'all11_complete':False}
(bib/'final-audit-v1.json').open('x',encoding='utf-8').write(json.dumps(out,indent=2))
print(json.dumps(out))
