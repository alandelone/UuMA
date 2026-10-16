from __future__ import annotations
from contextlib import closing
import json
import os
from pathlib import Path
import re
import socket
import sqlite3
import subprocess
import sys
import tempfile

REPO = Path(__file__).resolve().parents[1]
OUT = REPO / '.tmp/scholar-ca07-native-v1'
sys.path.insert(0, str(REPO / '.tmp/scholar-g11-parallel-v1'))
from runtime_copy_and_serve_v8 import product_guard, snapshot, digest, read_json, exclusive_json
CONTRACT = read_json(REPO / '.tmp/scholar-ca07-source-audit-v1/copied-fixture-contract.json')
SOURCE = Path(CONTRACT['source_db'])

def snap(db):
    return json.loads(json.dumps(snapshot(db), ensure_ascii=False))

def source_guard(receipt):
    assert digest(SOURCE) == CONTRACT['source_raw_sha256']
    assert snap(SOURCE) == read_json(OUT / 'source-before.json')
    assert product_guard() == receipt['source_vector']

def prepare():
    OUT.mkdir()
    assert digest(SOURCE) == CONTRACT['source_raw_sha256']
    assert SOURCE.stat().st_size == CONTRACT['source_raw_bytes']
    before = snap(SOURCE)
    assert len(before['tables']) == 83
    root = Path(tempfile.mkdtemp(prefix='scui-ca07-native-')).resolve()
    (root / 'data').mkdir()
    exclusive_json(OUT / 'allocated.json', {'root': str(root)})
    target = root / 'data/catalog.db'
    with closing(sqlite3.connect(SOURCE.as_uri() + '?mode=ro', uri=True)) as src:
        with closing(sqlite3.connect(target)) as dst:
            src.backup(dst)
    assert snap(target) == before
    exclusive_json(OUT / 'source-before.json', before)
    sys.path.insert(0, str(REPO.parent / 'RSTV4/src'))
    from rstv4.database import initialize_catalog, CATALOG_VERSION
    assert CATALOG_VERSION == 13
    initialize_catalog(target)
    after = snap(target)
    expected_added = read_json(REPO / '.tmp/scholar-g11-upstream-native-prepare-v1/migration-audit.json')['new_empty_tables']
    assert sorted(set(after['tables']) - set(before['tables'])) == expected_added
    assert all(after['tables'][name]['rows'] == [] for name in expected_added)
    extensions = {}
    for name, old in before['tables'].items():
        current = after['tables'][name]
        assert set(old['columns']) <= set(current['columns'])
        if name == 'schema_version':
            assert len(old['rows']) == len(current['rows']) == 1
            a = dict(zip(old['columns'], old['rows'][0]))
            b = dict(zip(current['columns'], current['rows'][0]))
            assert a['component'] == b['component'] == 'catalog' and a['version'] == 5 and b['version'] == 13
            assert set(a) == set(b) == {'component', 'version', 'applied_at'}
            continue
        projected = [[row[current['columns'].index(col)] for col in old['columns']] for row in current['rows']]
        assert sorted(map(lambda x: json.dumps(x,sort_keys=True), projected)) == sorted(map(lambda x: json.dumps(x,sort_keys=True), old['rows'])), name
        added = set(current['columns']) - set(old['columns'])
        if added:
            extensions[name] = sorted(added)
            assert all(row[current['columns'].index(col)] in (None, 0, '', '[]', '{}') for row in current['rows'] for col in added)
    lookup = {(row[0], row[1]): row for row in after['schema']}
    uniqueness = r',\s*UNIQUE\s*\(\s*parse_run_id\s*,\s*prompt_version\s*,\s*context_builder_version\s*\)'
    for row in before['schema']:
        key = row[0], row[1]
        if row[0] == 'table' and row[1] == 'skeleton_runs':
            assert lookup[key] == [*row[:3], re.sub(uniqueness, '', row[3])]
        elif row[0] == 'index' and row[1] == 'sqlite_autoindex_skeleton_runs_2':
            assert key not in lookup
        else:
            assert lookup[key] == row, key
    exclusive_json(OUT / 'after-migration.json', after)
    exclusive_json(OUT / 'migration-audit.json', {'old_tables': 83, 'new_tables': 105, 'new_empty_tables': expected_added,
                     'old_fields_and_rows_exact': True, 'old_column_extensions': extensions,
                     'only_old_schema_change': 'Documented skeleton history uniqueness removal'})
    receipt = {'root': str(root), 'source': str(SOURCE), 'source_vector': product_guard(),
               'source_raw_sha256': digest(SOURCE), 'worker_started': False, 'model_calls_allowed': 0}
    exclusive_json(OUT / 'prepared.json', receipt)
    source_guard(receipt)
    with (OUT / 'server.log').open('x', encoding='utf-8') as log:
        child = subprocess.Popen([str(REPO / '.uuma-local/scholar-collection-verification-v1/Scripts/python.exe'),
                                  str(Path(__file__).resolve()), 'serve'], cwd=REPO,
                                 stdout=log, stderr=subprocess.STDOUT, creationflags=subprocess.CREATE_NO_WINDOW)
    exclusive_json(OUT / 'launched.json', {'pid': child.pid})
    print(json.dumps({'status': 'PASS_EXACT_COPY_AND_EXPLICIT_MIGRATION_NATIVE_PENDING', 'root': str(root)}))

def serve():
    import uvicorn
    from fastapi.responses import JSONResponse, Response
    sys.path.insert(0, str(REPO.parent / 'RSTV4/src'))
    from rstv4.catalog_web import create_app
    receipt = read_json(OUT / 'prepared.json')
    source_guard(receipt)
    root = Path(receipt['root'])
    baseline = read_json(OUT / 'after-migration.json')
    app = create_app(root)
    class Deny:
        def analyze(self, *_args, **_kwargs):
            raise RuntimeError('Read-only copied Catalog denies all model work')
    app.state.discussions.gateway = Deny()
    app.state.fieldkg_semantics.gateway = Deny()
    assert snap(root / 'data/catalog.db') == baseline
    (OUT / 'queries').mkdir()
    count = 0
    @app.middleware('http')
    async def bound(request, call_next):
        nonlocal count
        if request.method in {'GET','HEAD','OPTIONS'}:
            return await call_next(request)
        if request.method == 'POST' and request.url.path == '/api/catalog/papers/query':
            count += 1
            index = count
            body = await request.json()
            response = await call_next(request)
            raw = b''.join([part async for part in response.body_iterator])
            exclusive_json(OUT / 'queries' / f'{index:03}.json',
                           {'request': body, 'status_code': response.status_code, 'response': json.loads(raw)})
            return Response(raw, status_code=response.status_code, headers=dict(response.headers))
        return JSONResponse({'detail': 'Copied Catalog permits only listing reads'}, status_code=403)
    sock = socket.socket()
    sock.bind(('127.0.0.1',0)); sock.listen(128)
    port = sock.getsockname()[1]
    exclusive_json(OUT / 'server-ready.json', {'pid': os.getpid(), 'port': port, 'root': str(root),
                     'url': f'http://127.0.0.1:{port}/?view=all', 'workers_started': 0, 'model_calls_allowed': 0})
    uvicorn.Server(uvicorn.Config(app,log_level='warning')).run(sockets=[sock])

def audit():
    receipt = read_json(OUT / 'prepared.json')
    source_guard(receipt)
    final = snap(Path(receipt['root']) / 'data/catalog.db')
    assert final == read_json(OUT / 'after-migration.json')
    evidence = read_json(OUT / 'native-cases.json')
    definitions = {
        'default-page1': ('p.updated_at DESC,p.paper_id ASC', '', 0),
        'default-page2': ('p.updated_at DESC,p.paper_id ASC', '', 50),
        'default-back-page1': ('p.updated_at DESC,p.paper_id ASC', '', 0),
        'mixed-priority': ('(p.published_year IS NULL),p.published_year DESC,p.updated_at ASC,p.paper_id ASC', '', 0),
        'reversed-priority': ('p.updated_at ASC,(p.published_year IS NULL),p.published_year DESC,p.paper_id ASC', '', 0),
        'tied-page1': ('p.paper_id ASC', "AND p.published_year IS NULL AND p.authors_json='[]'", 0),
        'tied-page2': ('p.paper_id ASC', "AND p.published_year IS NULL AND p.authors_json='[]'", 50),
        'tied-back-page1': ('p.paper_id ASC', "AND p.published_year IS NULL AND p.authors_json='[]'", 0),
    }
    assert set(evidence) == set(definitions)
    with closing(sqlite3.connect(SOURCE.as_uri()+'?mode=ro',uri=True)) as conn:
        for name, (order, condition, offset) in definitions.items():
            base = "FROM papers p WHERE NOT EXISTS (SELECT 1 FROM catalog_quarantine q WHERE q.paper_id=p.paper_id) " + condition
            total = conn.execute('SELECT COUNT(*) ' + base).fetchone()[0]
            expected = [r[0] for r in conn.execute('SELECT p.paper_id '+base+' ORDER BY '+order+' LIMIT 50 OFFSET ?', (offset,))]
            case = evidence[name]
            assert len(case['ids']) == 50 and len(set(case['ids'])) == 50
            assert case['ids'] == expected, name
            assert case['total'] == total == (1117 if name.startswith('tied') else 1197)
            assert case['page'] == (offset // 50 + 1)
    assert set(evidence['default-page1']['ids']).isdisjoint(evidence['default-page2']['ids'])
    assert set(evidence['tied-page1']['ids']).isdisjoint(evidence['tied-page2']['ids'])
    assert evidence['mixed-priority']['ids'] != evidence['reversed-priority']['ids']
    for name, case in evidence.items():
        query = read_json(OUT / 'queries' / case['query_file'])
        assert query['status_code'] == 200
        response = query['response']
        assert response['page_size'] == 50 and response['page'] == case['page'] and response['total'] == case['total']
        assert [row['paper_id'] for row in response['items']] == case['ids']
        request = query['request']
        if name.startswith('mixed'):
            assert request['sorts'] == [{'field':'published_year','direction':'desc'},{'field':'updated_at','direction':'asc'}]
        elif name.startswith('reversed'):
            assert request['sorts'] == [{'field':'updated_at','direction':'asc'},{'field':'published_year','direction':'desc'}]
        elif name.startswith('tied'):
            assert request['sorts'] == [{'field':'published_year','direction':'desc'},{'field':'authors','direction':'asc'}]
    exclusive_json(OUT / 'final-all-tables.json', final)
    exclusive_json(OUT / 'audit.json', {'status':'PASS_CA07_NATIVE_MULTI_SORT_STABLE_TIES_AND_50_PAGINATION',
                    'native_cases':list(definitions), 'original_source_bytes_and_83_tables_exact':True,
                    'owned_105_tables_schema_and_rows_exact':True,'new_models_workers_or_papers':0,
                    'all11_complete':False})
    print('PASS_CA07_NATIVE_MULTI_SORT_STABLE_TIES_AND_50_PAGINATION')

if __name__ == '__main__':
    {'prepare':prepare,'serve':serve,'audit':audit}[sys.argv[1]]()
