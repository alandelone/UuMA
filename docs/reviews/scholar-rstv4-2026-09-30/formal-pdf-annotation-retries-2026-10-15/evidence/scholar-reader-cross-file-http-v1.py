from contextlib import closing
from pathlib import Path
import hashlib
import json
import os
import shutil
import socket
import sqlite3
import sys
import tempfile
import threading
import urllib.error
import urllib.request

import uvicorn
from pypdf import PdfWriter
from pypdf.generic import DecodedStreamObject, DictionaryObject, NameObject

repo = Path(__file__).resolve().parents[1]
source = repo.parent / 'RSTV4'
sys.path[:0] = [str(source / 'src'), str(repo / '.tmp/scholar-g11-parallel-v1')]
from runtime_copy_and_serve import snapshot
from rstv4.catalog_web import create_app

here = repo / '.tmp/scholar-reader-cross-file-http-v1'
here.mkdir(exist_ok=False)
sha = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()
snap = lambda p: json.loads(json.dumps(snapshot(p), ensure_ascii=False))
original = Path(json.loads((repo / '.tmp/scholar-reader-http-v2/allocated.json').read_text())['root'])
old = snap(original / 'data/catalog.db')
files = {p.relative_to(original).as_posix(): sha(p) for p in original.rglob('*')
         if p.is_file() and not p.name.endswith(('-wal', '-shm'))}
frozen = json.loads((repo / '.tmp/scholar-reader-frontend-v3/source-before.json').read_text())


def put(name, value):
    with (here / name).open('x', encoding='utf-8') as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2)


root = Path(tempfile.mkdtemp(prefix='scui-reader-cross-file-')).resolve()
put('allocated.json', {'root': str(root), 'source': str(original), 'software_fixture': True})
shutil.copytree(original / 'data', root / 'data', ignore=lambda _p, names: [
    n for n in names if n in {'catalog.db', 'catalog.db-wal', 'catalog.db-shm'}])
db = root / 'data/catalog.db'
with closing(sqlite3.connect((original / 'data/catalog.db').as_uri() + '?mode=ro', uri=True)) as src:
    with closing(sqlite3.connect(db)) as dst:
        src.backup(dst)
assert snap(db) == old
writer = PdfWriter()
page = writer.add_blank_page(width=300, height=400)
font = DictionaryObject({NameObject('/Type'): NameObject('/Font'),
                        NameObject('/Subtype'): NameObject('/Type1'),
                        NameObject('/BaseFont'): NameObject('/Helvetica')})
page[NameObject('/Resources')] = DictionaryObject({NameObject('/Font'): DictionaryObject({
    NameObject('/F1'): writer._add_object(font)})})
content = DecodedStreamObject()
content.set_data(b'BT /F1 14 Tf 30 330 Td (Alternate Software Source Title) Tj ET')
page[NameObject('/Contents')] = writer._add_object(content)
second = root / 'second-version.pdf'
writer.write(second)
with sqlite3.connect(db) as conn:
    conn.execute("""INSERT INTO source_file_versions SELECT 'second-version',paper_id,?,?,
                 mime_type,?,'SOFTWARE_FIXTURE',NULL,'NEEDS_REVIEW',validation_json,
                 created_at FROM source_file_versions WHERE file_version_id='f2'""",
                 (sha(second), second.stat().st_size, str(second)))
app = create_app(root)
before = snap(db)
assert before['schema'] == old['schema']
for name, table in old['tables'].items():
    if name == 'source_file_versions':
        assert len(before['tables'][name]['rows']) == len(table['rows']) + 1
        assert all(row in before['tables'][name]['rows'] for row in table['rows'])
    else:
        assert before['tables'][name] == table, name
put('before.json', before)
sock = socket.socket()
sock.bind(('127.0.0.1', 0))
sock.listen(128)
port = sock.getsockname()[1]
server = uvicorn.Server(uvicorn.Config(app, lifespan='off', log_level='warning'))
worker = threading.Thread(target=server.run, kwargs={'sockets': [sock]}, daemon=True)
worker.start()
put('server.json', {'pid': os.getpid(), 'port': port, 'lifespan': 'off'})
counter = 0


def call(label, path, payload=None, expected=200, unchanged=False):
    global counter
    baseline = snap(db)
    req = urllib.request.Request(f'http://127.0.0.1:{port}{path}',
                                 data=json.dumps(payload).encode() if payload is not None else None,
                                 headers={'Content-Type': 'application/json'})
    try:
        response = urllib.request.urlopen(req, timeout=30)
    except urllib.error.HTTPError as error:
        response = error
    with response:
        result = {'method': req.get_method(), 'path': path, 'request': payload,
                  'status': response.status, 'body': json.loads(response.read())}
    counter += 1
    put(f'http-{counter:02d}-{label}.json', result)
    put(f'after-{counter:02d}-{label}.json', snap(db))
    assert result['status'] == expected, result
    if unchanged:
        assert snap(db) == baseline, label
    return result['body']


complete = False
try:
    path = '/api/catalog/review/cases/f2/annotations'
    head = next(a for a in call('old-head', path) if a['field_name'] == 'TITLE')
    payload = {'submission_id': 'software-cross-file-note', 'field_name': 'TITLE', 'decision': 'FOUND',
               'page_number': head['page_number'], 'word_start': head['word_start'],
               'word_end': head['word_end'], 'comment': 'A guarded note on the first PDF version.',
               'expected_annotation_id': head['annotation_id'],
               'expected_catalog_value': {'value': head['value_after']}}
    saved = call('guarded-note', path, payload, 201)
    words = call('second-source-words', '/api/catalog/files/second-version/pages/1/text')['words']
    assert ' '.join(word['text'] for word in words) == 'Alternate Software Source Title'
    alternate = {'submission_id': 'software-second-file-title', 'field_name': 'TITLE',
                 'decision': 'FOUND', 'page_number': 1, 'word_start': 0, 'word_end': len(words)-1,
                 'comment': 'Software second source version selection.', 'expected_annotation_id': ''}
    call('other-version-title', '/api/catalog/review/cases/second-version/annotations', alternate, 201)
    call('old-file-note-conflict', path, {**payload, 'submission_id': 'software-stale-other-file',
         'expected_annotation_id': saved['annotation_id']}, 409, unchanged=True)
    replay = call('original-note-retry', path, payload, 201, unchanged=True)
    assert replay['annotation_id'] == saved['annotation_id']
    call('changed-value-same-key', path, {**payload,
         'expected_catalog_value': {'value': 'Alternate Software Source Title'}}, 409, unchanged=True)
    doi = next(a for a in call('latest-doi-head', path) if a['field_name'] == 'DOI')
    call('null-catalog-conflict', path, {'submission_id': 'software-null-catalog-expectation',
         'field_name': 'DOI', 'decision': 'ABSENT', 'expected_annotation_id': doi['annotation_id'],
         'expected_catalog_value': {'value': None}}, 409, unchanged=True)
    current = call('current-other-version', '/api/catalog/papers/p2')
    assert current['title'] == 'Alternate Software Source Title'
    after = snap(db)
    changed = [name for name in before['tables'] if before['tables'][name] != after['tables'][name]]
    assert set(changed) == {'papers', 'catalog_review_annotations'}
    assert after['schema'] == before['schema']
    assert snap(original / 'data/catalog.db') == old
    assert {p.relative_to(original).as_posix(): sha(p) for p in original.rglob('*')
            if p.is_file() and not p.name.endswith(('-wal', '-shm'))} == files
    assert all(sha(source / name) == digest for name, digest in frozen.items())
    put('audit.json', {'status': 'PASS', 'http_requests': counter, 'tables': 110,
                       'unchanged_tables': 108, 'changed_tables': changed,
                       'source_file_versions_added_before_baseline': 1,
                       'annotation_events_added': 2, 'original_copy_exact': True,
                       'source_words_checked': True, 'jobs_models_gpu_workers_executed': 0,
                       'native_browser_executed': False, 'all11_complete': False})
    complete = True
finally:
    server.should_exit = True
    worker.join(timeout=15)
    check = socket.socket()
    free = check.connect_ex(('127.0.0.1', port)) != 0
    check.close()
    app.state.discussions.shutdown()
    put('terminal.json', {'completed': complete, 'server_stopped': not worker.is_alive(), 'port_free': free})
    assert not worker.is_alive() and free
print(json.dumps({'status': 'PASS', 'http_requests': counter, 'root': str(root)}))
