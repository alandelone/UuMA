from pathlib import Path
import hashlib
import inspect
import json
import os
import shutil
import sqlite3
import subprocess
import sys
import threading

root = Path.cwd()
out = root/'.tmp/scholar-intent-correspondence-rollback-baseline-v3'

if len(sys.argv) == 1:
    out.mkdir(exist_ok=False)
    shutil.copytree(root.parent/'RSTV4/src', out/'old-src', ignore=shutil.ignore_patterns('__pycache__'))
    before = root/'.tmp/scholar-intent-correspondence-before-v1/source/RSTV4/src/rstv4'
    baseline = json.loads((root/'.tmp/scholar-intent-correspondence-before-v1/baseline.json').read_text(encoding='utf-8'))
    for name in ['studio.py','studio_context.py','studio_structure.py','studio_templates.py']:
        shutil.copy2(before/name, out/'old-src/rstv4'/name)
        assert hashlib.sha256((out/'old-src/rstv4'/name).read_bytes()).hexdigest() == baseline['source_sha256']['RSTV4/src/rstv4/'+name]
    runtime = root/'.uuma-local/scholar-collection-verification-v1/Scripts/python.exe'
    outcomes = {}
    for variant in ['current','before']:
        result = subprocess.run([str(runtime),'-X','utf8',str(Path(__file__).resolve()),variant],
                                capture_output=True,text=True,encoding='utf-8',env={**os.environ,'PYTHONUTF8':'1'})
        (out/f'{variant}.log').write_text(result.stdout+'\n'+result.stderr,encoding='utf-8')
        outcomes[variant] = result.returncode
    print(json.dumps({'outcomes':outcomes,'retained_dir':str(out)}))
    raise SystemExit(0)

variant = sys.argv[1]
if variant == 'before': sys.path.insert(0, str(out/'old-src'))
sys.path.insert(0, str(root.parent/'RSTV4/tests'))
import pytest
import rstv4.studio
print('ACTUAL_STUDIO_SOURCE',rstv4.studio.__file__,hashlib.sha256(Path(rstv4.studio.__file__).read_bytes()).hexdigest())
original_read = Path.read_bytes
captures = []

def snapshot(path):
    with sqlite3.connect(path.as_uri()+'?mode=ro',uri=True) as conn:
        tables = [r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")]
        rows = {name: sorted([repr(tuple(row)) for row in conn.execute('SELECT * FROM "'+name.replace('"','""')+'"')]) for name in tables}
        params = {key:conn.execute('PRAGMA '+key).fetchone()[0] for key in ['page_size','page_count','freelist_count','schema_version','auto_vacuum']}
        page4 = 'DBSTAT_UNAVAILABLE_IN_OBSERVED_BUILD'
    return {'rows':rows,'params':params,'page4':page4,'threads':[t.name for t in threading.enumerate()]}

def recording_read(path):
    raw = original_read(path)
    caller = inspect.currentframe().f_back
    if path.name == 'catalog.db' and caller.f_code.co_name == 'test_adoption_record_failure_rolls_back_document_and_operation':
        number = len(captures)
        with (out/f'{variant}-{number}.db').open('xb') as stream: stream.write(raw)
        captures.append((raw,snapshot(path)))
    return raw

class CapturePlugin:
    def pytest_runtest_call(self, item):
        Path.read_bytes = recording_read
    def pytest_runtest_teardown(self, item):
        Path.read_bytes = original_read

status = pytest.main(['-q',str(root.parent/'RSTV4/tests/test_studio_templates.py')+'::test_adoption_record_failure_rolls_back_document_and_operation'],plugins=[CapturePlugin()])
Path.read_bytes = original_read
assert len(captures) == 2
before_raw, before_state = captures[0]
after_raw, after_state = captures[1]
diffs = [i for i,(a,b) in enumerate(zip(before_raw,after_raw)) if a!=b]
page_size = before_state['params']['page_size']
trunk = int.from_bytes(before_raw[32:36], 'big')
trunks = []
leaves = []
while trunk:
    assert trunk not in trunks
    trunks.append(trunk)
    at = (trunk-1)*page_size
    count = int.from_bytes(before_raw[at+4:at+8], 'big')
    assert count <= page_size//4-2
    leaves.extend(int.from_bytes(before_raw[at+8+n*4:at+12+n*4], 'big') for n in range(count))
    trunk = int.from_bytes(before_raw[at:at+4], 'big')
assert len(trunks)+len(leaves)==before_state['params']['freelist_count']
changed_pages=sorted({i//page_size+1 for i in diffs})
result = {'freelist_trunks_before':trunks,'freelist_leaves_before':leaves,
          'changed_pages':changed_pages,'only_before_free_leaf_pages_changed':bool(diffs) and set(changed_pages).issubset(set(leaves)),
          'pytest_exit':int(status),'variant':variant,'source':rstv4.studio.__file__,
          'bytes_equal':before_raw==after_raw,'rows_equal':before_state['rows']==after_state['rows'],
          'before':{k:v for k,v in before_state.items() if k!='rows'},'after':{k:v for k,v in after_state.items() if k!='rows'},
          'changed_tables':[name for name in before_state['rows'] if before_state['rows'][name]!=after_state['rows'][name]],
          'byte_differences':len(diffs),'first_differences':diffs[:30]}
(out/f'{variant}.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
print(json.dumps(result))
raise SystemExit(int(status))
