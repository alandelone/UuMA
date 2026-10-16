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

repo = Path(__file__).resolve().parents[1]
source = repo.parent / 'RSTV4'
sys.path[:0] = [str(source / 'src'), str(source / 'tests'),
                str(repo / '.tmp/scholar-g11-parallel-v1')]
from runtime_copy_and_serve import snapshot
from test_catalog_web import seed_catalog
from rstv4.catalog_web import create_app

here = repo / '.tmp/scholar-reader-http-v1'
here.mkdir(exist_ok=False)
original = Path('C:/Users/Alandelone/AppData/Local/Temp/scui-publication-chain-2rsgo3jx')
sha = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()
snap = lambda p: json.loads(json.dumps(snapshot(p), ensure_ascii=False))


def put(name, value):
    with (here / name).open('x', encoding='utf-8') as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2)


frozen = json.loads((repo / '.tmp/scholar-reader-frontend-v2/source-before.json').read_text())
old_files = {p.relative_to(original).as_posix(): sha(p) for p in original.rglob('*')
             if p.is_file() and not p.name.endswith(('-wal', '-shm'))}
old = snap(original / 'data/catalog.db')
assert len(old['tables']) == 110
put('original-files.json', old_files)
put('original-before.json', old)
root = Path(tempfile.mkdtemp(prefix='scui-reader-annotations-')).resolve()
put('allocated.json', {'root': str(root), 'source': str(original), 'software_fixture': True})
shutil.copytree(original / 'data', root / 'data', ignore=lambda _p, names: [
    n for n in names if n in {'catalog.db', 'catalog.db-wal', 'catalog.db-shm'}])
db = root / 'data/catalog.db'
with closing(sqlite3.connect((original / 'data/catalog.db').as_uri() + '?mode=ro', uri=True)) as src:
    with closing(sqlite3.connect(db)) as dst:
        src.backup(dst)
assert snap(db) == old
seed_catalog(root)
with sqlite3.connect(db) as conn:
    conn.execute("INSERT INTO paper_identities VALUES(?,?,?,?,?,?,?)", (
        'software-old-doi', 'p2', 'DOI', '10.1/b', 'CONFIRMED', 'SOFTWARE_FIXTURE', 'now'))
    conn.execute("""INSERT INTO source_file_versions SELECT 'software-conflict-file','p3',
                 sha256,size_bytes,mime_type,storage_path,'SOFTWARE_FIXTURE',NULL,
                 'NEEDS_REVIEW',validation_json,created_at FROM source_file_versions
                 WHERE file_version_id='f2'""")
app = create_app(root)
before = snap(db)
assert before['schema'] == old['schema']
seed_tables = {'papers', 'paper_identities', 'source_file_versions'}
for name, table in old['tables'].items():
    if name not in seed_tables:
        assert before['tables'][name] == table, name
    else:
        assert all(row in before['tables'][name]['rows'] for row in table['rows']), name
put('before.json', before)
pdf_hash = sha(root / 'sample.pdf')

sock = socket.socket()
sock.bind(('127.0.0.1', 0))
sock.listen(128)
port = sock.getsockname()[1]
server = uvicorn.Server(uvicorn.Config(app, lifespan='off', log_level='warning'))
worker = threading.Thread(target=server.run, kwargs={'sockets': [sock]}, daemon=True)
worker.start()
put('server.json', {'pid': os.getpid(), 'port': port, 'lifespan': 'off', 'models': 0})
counter = 0


def call(label, path, payload=None, expected=200, binary=False):
    global counter
    req = urllib.request.Request(f'http://127.0.0.1:{port}{path}',
                                 data=json.dumps(payload).encode() if payload is not None else None,
                                 headers={'Content-Type': 'application/json'})
    try:
        response = urllib.request.urlopen(req, timeout=30)
    except urllib.error.HTTPError as error:
        response = error
    with response:
        raw = response.read()
        value = {'method': req.method, 'path': path, 'request': payload,
                 'status': response.status,
                 'body': {'sha256': hashlib.sha256(raw).hexdigest(), 'size': len(raw)}
                 if binary else json.loads(raw)}
    counter += 1
    put(f'http-{counter:02d}-{label}.json', value)
    put(f'after-{counter:02d}-{label}.json', snap(db))
    assert value['status'] == expected, value
    return value['body']


def post(label, field, decision, head='', *, selected=None, comment='', case='f2', expected=201):
    payload = {'submission_id': f'software-reader-{label}', 'field_name': field,
               'decision': decision, 'expected_annotation_id': head, 'comment': comment,
               'page_number': 1 if selected else None,
               'word_start': selected[0] if selected else None,
               'word_end': selected[1] if selected else None}
    return call(label, f'/api/catalog/review/cases/{case}/annotations', payload, expected), payload


def unchanged(label, path, payload, expected):
    baseline = snap(db)
    result = call(label, path, payload, expected)
    assert snap(db) == baseline, label
    return result


def paper():
    with sqlite3.connect(db) as conn:
        conn.row_factory = sqlite3.Row
        return dict(conn.execute("SELECT * FROM papers WHERE paper_id='p2'").fetchone())


completed = False
try:
    queue = call('queue', '/api/catalog/review/cases')
    assert any(c['case_id'] == 'f2' for c in queue)
    call('pdf-info', '/api/catalog/files/f2/pdf-info')
    words = call('source-words', '/api/catalog/files/f2/pages/1/text')['words']
    title_range = (0, 3)
    assert ' '.join(w['text'] for w in words[:4]) == 'Solar Energy B Revised'
    doi_index = next(i for i, word in enumerate(words) if word['text'] == '10.1234/b')
    doi_range = (doi_index, doi_index)
    assert call('source-pdf', '/api/catalog/files/f2/pdf', binary=True)['sha256'] == pdf_hash
    title, title_payload = post('title', 'TITLE', 'FOUND', selected=title_range)
    doi, _ = post('doi', 'DOI', 'FOUND', selected=doi_range)
    note, note_payload = post('doi-note', 'DOI', 'FOUND', doi['annotation_id'], selected=doi_range,
                              comment='Software acceptance note anchored to these physical PDF words.')
    annotation_path = '/api/catalog/review/cases/f2/annotations'
    repeated = unchanged('exact-note-retry', annotation_path, note_payload, 201)
    assert repeated['annotation_id'] == note['annotation_id']
    unchanged('collision-same-key', annotation_path, {**note_payload, 'comment': 'changed intent'}, 409)
    unchanged('stale-note-source', annotation_path, {**note_payload,
              'submission_id': 'software-stale-head', 'expected_annotation_id': doi['annotation_id']}, 409)
    absent, _ = post('doi-absent', 'DOI', 'ABSENT', note['annotation_id'])
    assert paper()['doi'] == '10.1/b' and paper()['canonical_key'] == 'solar-b'
    restored, _ = post('doi-reselect', 'DOI', 'FOUND', absent['annotation_id'], selected=doi_range)
    wrong, _ = post('wrong-pdf', 'PDF', 'WRONG_PDF')
    assert paper()['title'] == 'Solar Energy B' and paper()['doi'] == '10.1/b'
    records = call('reversal-history', annotation_path)
    latest = {field: next(a for a in records if a['field_name'] == field) for field in ['TITLE', 'DOI']}
    assert all(a['decision'] == 'REVERTED' for a in latest.values())
    baseline = snap(db)
    post('still-blocked', 'TITLE', 'FOUND', latest['TITLE']['annotation_id'], selected=title_range, expected=409)
    assert snap(db) == baseline
    assert call('pdf-retained', '/api/catalog/files/f2/pdf', binary=True)['sha256'] == pdf_hash
    post('reopen-pdf', 'PDF', 'REOPEN', wrong['annotation_id'])
    current_title, _ = post('title-after-reopen', 'TITLE', 'FOUND', latest['TITLE']['annotation_id'], selected=title_range)
    post('doi-after-reopen', 'DOI', 'FOUND', latest['DOI']['annotation_id'], selected=doi_range)
    old_retry = unchanged('historical-title-retry', annotation_path, title_payload, 201)
    assert old_retry['annotation_id'] == title['annotation_id']
    baseline = snap(db)
    post('other-paper-doi-conflict', 'DOI', 'FOUND', selected=doi_range,
         case='software-conflict-file', expected=409)
    assert snap(db) == baseline
    assert call('other-file-history', '/api/catalog/review/cases/software-conflict-file/annotations') == []
    post('title-note', 'TITLE', 'FOUND', current_title['annotation_id'], selected=title_range,
         comment='Software title note; original page and word range retained.')
    records = call('reopened-history', annotation_path)
    current = call('current-catalog', '/api/catalog/papers/p2')
    assert current['title'] == 'Solar Energy B Revised' and current['doi'] == '10.1234/b'
    assert len(records) == 12
    for record in records:
        assert record['paper_id'] == 'p2' and record['file_version_id'] == 'f2'
        assert record['reviewer_label'] and record['created_at']
        if record['decision'] == 'FOUND':
            selected = words[record['word_start']:record['word_end'] + 1]
            assert record['page_number'] == 1
            assert record['selected_text'] == ' '.join(word['text'] for word in selected)
    after = snap(db)
    changed = [name for name in before['tables'] if before['tables'][name] != after['tables'][name]]
    assert set(changed) == {'papers', 'paper_identities', 'catalog_review_annotations'}
    assert after['schema'] == before['schema']
    columns = before['tables']['papers']['columns']
    idx = columns.index('paper_id')
    assert [r for r in before['tables']['papers']['rows'] if r[idx] != 'p2'] == [
        r for r in after['tables']['papers']['rows'] if r[idx] != 'p2']
    assert sha(root / 'sample.pdf') == pdf_hash
    assert snap(original / 'data/catalog.db') == old
    assert {p.relative_to(original).as_posix(): sha(p) for p in original.rglob('*')
            if p.is_file() and not p.name.endswith(('-wal', '-shm'))} == old_files
    assert all(sha(source / name) == digest for name, digest in frozen.items())
    put('audit.json', {'status': 'PASS', 'http_requests': counter, 'tables': len(after['tables']),
                       'unchanged_tables': 107, 'changed_tables': changed,
                       'annotation_events': len(records), 'source_words_checked': True,
                       'old_original_rows_and_files_exact': True, 'schema_unchanged': True,
                       'models_jobs_workers_gpu_executed': 0, 'native_browser_executed': False,
                       'all11_complete': False})
    completed = True
finally:
    server.should_exit = True
    worker.join(timeout=15)
    stopped = not worker.is_alive()
    check = socket.socket()
    free = check.connect_ex(('127.0.0.1', port)) != 0
    check.close()
    app.state.discussions.shutdown()
    put('terminal.json', {'completed': completed, 'server_stopped': stopped, 'port_free': free})
    assert stopped and free
print(json.dumps({'status': 'PASS', 'http_requests': counter, 'root': str(root),
                  'all11_complete': False}))
