from pathlib import Path
import hashlib
import json
import sqlite3
import sys
import tempfile
import threading

root = Path.cwd()
sys.path.insert(0, str(root.parent/'RSTV4/tests'))
from test_studio_templates import fixture

out = root/'.tmp/scholar-intent-correspondence-rollback-diagnostic-v1'
out.mkdir(exist_ok=False)
work = Path(tempfile.mkdtemp(prefix='sci-roll-'))
service, manuscript_id, _, _, request = fixture(work)

def state():
    with sqlite3.connect(service.db_path.as_uri()+'?mode=ro', uri=True) as conn:
        names = [row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")]
        rows = {name: sorted([tuple(row) for row in conn.execute('SELECT * FROM "'+name.replace('"','""')+'"')],key=repr) for name in names}
        params = {key:conn.execute('PRAGMA '+key).fetchone()[0] for key in ['page_size','page_count','freelist_count','schema_version','auto_vacuum']}
    raw = service.db_path.read_bytes()
    return rows, params, raw

save = service.save_document
def interrupted(*args, **kwargs):
    saved = save(*args, **kwargs)
    assert saved['document_revision'] == 2
    raise RuntimeError('software fixture failure after document writes')
service.save_document = interrupted
before_rows, before_params, before_raw = state()
threads_before = [thread.name for thread in threading.enumerate()]
try:
    service.apply_template(manuscript_id, request)
    raise AssertionError('Expected rollback exception')
except RuntimeError as exc:
    assert str(exc) == 'software fixture failure after document writes'
after_rows, after_params, after_raw = state()
(out/'before.db').write_bytes(before_raw)
(out/'after.db').write_bytes(after_raw)
diffs = [n for n,(a,b) in enumerate(zip(before_raw,after_raw)) if a!=b]
changed_tables = [name for name in before_rows if before_rows[name] != after_rows[name]]
data = {'fixture_root':str(work),'threads_before':threads_before,'threads_after':[t.name for t in threading.enumerate()],
        'before_params':before_params,'after_params':after_params,'bytes_equal':before_raw==after_raw,
        'row_equality':not changed_tables,'changed_tables':changed_tables,'different_byte_count':len(diffs),
        'first_differences':diffs[:30],'before_sha256':hashlib.sha256(before_raw).hexdigest(),
        'after_sha256':hashlib.sha256(after_raw).hexdigest()}
(out/'diagnostic.json').write_text(json.dumps(data,indent=2),encoding='utf-8')
print(json.dumps(data))
assert before_rows == after_rows
assert before_raw == after_raw
