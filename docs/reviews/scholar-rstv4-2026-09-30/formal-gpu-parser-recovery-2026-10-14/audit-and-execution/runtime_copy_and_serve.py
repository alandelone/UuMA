from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import socket
import sqlite3
import tempfile
from contextlib import closing
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
RSTV4 = REPO.parent / 'RSTV4'
RECEIPT = HERE / 'runtime-copy-receipt.json'


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read_json(path: Path):
    return json.loads(path.read_text(encoding='utf-8'))


def exclusive_json(path: Path, value) -> None:
    with path.open('x', encoding='utf-8') as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2)
        stream.write('\n')


def product_guard() -> dict[str, str]:
    declared = read_json(HERE / 'preparation-receipt.json')['source_vectors']
    expected = {item['path']: item['sha256'] for item in declared
                if Path(item['path']).is_relative_to(RSTV4)}
    expected.update(read_json(HERE / 'runtime-source-vector.json'))
    for name, expected_sha in expected.items():
        assert digest(Path(name)) == expected_sha, f'Prepared product source changed: {name}'
    return expected


def snapshot(db: Path) -> dict:
    with closing(sqlite3.connect(db.as_uri() + '?mode=ro', uri=True)) as conn:
        conn.execute('BEGIN')
        schema = conn.execute("SELECT type,name,tbl_name,sql FROM sqlite_master ORDER BY type,name").fetchall()
        result = {'schema': schema, 'tables': {}}
        for name, in conn.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"):
            quoted = '"' + name.replace('"', '""') + '"'
            cols = [row[1] for row in conn.execute('PRAGMA table_info(' + quoted + ')')]
            rows = conn.execute('SELECT * FROM ' + quoted).fetchall()
            encoded = [[{'__blob__': value.hex()} if isinstance(value, bytes) else value
                        for value in row] for row in rows]
            encoded.sort(key=lambda row: json.dumps(row, sort_keys=True, ensure_ascii=False))
            result['tables'][name] = {'columns': cols, 'rows': encoded}
        return result


def files(root: Path) -> dict[str, str]:
    # Include source DB and sidecars: fail on any external write during the copy.
    return {str(p.resolve()): digest(p) for p in sorted(root.rglob('*')) if p.is_file()}


def source_files(parent: dict, deep: dict) -> dict[str, str]:
    result = {}
    for name in [parent['root'], deep['root']]:
        result.update(files(Path(name).resolve()))
    for name in [parent['source_path'], parent['candidate']['path']]:
        p = Path(name).resolve()
        assert p.is_file(), f'Retained actual source unavailable: {p}'
        result[str(p)] = digest(p)
    assert digest(Path(parent['source_path'])) == '85f4078a0ae99a5c0b13894ce4bbf511c7e9302958512e738b7180dae1110f99'
    assert digest(Path(parent['candidate']['path'])) == parent['candidate']['sha256']
    return result


def check_sources(receipt: dict) -> None:
    for name, expected in receipt['protected_original_files'].items():
        assert digest(Path(name)) == expected, f'Original source bytes changed: {name}'


def verify_migration(before: dict, after: dict, version: int) -> dict:
    old_tables, new_tables = before['tables'], after['tables']
    assert set(old_tables) <= set(new_tables), 'Migration removed an original table'
    additions = set(new_tables) - set(old_tables)
    assert additions <= {'fieldkg_semantic_runs', 'fieldkg_semantic_objects', 'skeleton_source_outlines'}, additions
    for name in additions:
        assert not new_tables[name]['rows'], f'Unexpected seeded new migration table: {name}'
    for name, old in old_tables.items():
        actual = new_tables[name]
        assert actual['columns'] == old['columns'], f'Unexpected original column change: {name}'
        if name != 'schema_version':
            assert actual['rows'] == old['rows'], f'Original row changed in migration: {name}'
            continue
        original_rows = [dict(zip(old['columns'], row)) for row in old['rows']]
        actual_rows = [dict(zip(actual['columns'], row)) for row in actual['rows']]
        assert {row['component'] for row in actual_rows} == {row['component'] for row in original_rows}
        for old_row in original_rows:
            row = next(item for item in actual_rows if item['component'] == old_row['component'])
            if row['component'] == 'catalog' and old_row['version'] != version:
                assert row['version'] == version and row['applied_at']
                assert {k:v for k,v in row.items() if k not in {'version','applied_at'}} == {k:v for k,v in old_row.items() if k not in {'version','applied_at'}}
            else:
                assert row == old_row
    # All existing schema objects remain except the documented skeleton history uniqueness migration.
    lookup = {(row[0], row[1]): row for row in after['schema']}
    old_skeleton = next((row for row in before['schema'] if row[0]=='table' and row[1]=='skeleton_runs'), None)
    uniqueness = r',\s*UNIQUE\s*\(\s*parse_run_id\s*,\s*prompt_version\s*,\s*context_builder_version\s*\)'
    migrated_skeleton = bool(old_skeleton and re.search(uniqueness, old_skeleton[3]))
    for row in before['schema']:
        key = (row[0], row[1])
        if migrated_skeleton and row[0]=='table' and row[1]=='skeleton_runs':
            expected = (*row[:3], re.sub(uniqueness, '', row[3]))
            assert lookup.get(key) == expected, 'Only declared skeleton history uniqueness removal permitted'
        elif migrated_skeleton and row[0]=='index' and row[1]=='sqlite_autoindex_skeleton_runs_2':
            assert key not in lookup, 'Only old redundant unique autoindex may disappear'
        else:
            assert lookup.get(key) == row, f'Unexpected schema object change: {key}'
    return {'old_tables':len(old_tables), 'new_tables':len(new_tables), 'added_empty_tables':sorted(additions),
            'all_old_rows_preserved':True, 'catalog_version':version}


class DenyModels:
    def analyze(self, task, payload):
        raise RuntimeError('G11 serve/read-only boundary: all remote/model tasks denied')


def prepare() -> None:
    assert not RECEIPT.exists(), 'Do not replay exclusive copied-fixture preparation'
    vector = product_guard()
    parent_path = REPO / '.tmp/scholar-review-recovery-native-v1.json'
    deep_path = REPO / '.tmp/scholar-deep-read-native-v2.json'
    parent, deep = read_json(parent_path), read_json(deep_path)
    assert parent['status'] == 'PASS_ACTUAL_IDENTITY_REVIEW_AND_REAL_MINERU_PARSER_RECOVERY'
    assert parent['actual_local_mineru_executed'] and not parent['scientific_approval']
    assert deep['status'] == 'PASS_ACTUAL_QUICKREAD_SKELETON_ASSESSMENT_AND_FORMAL_READBACK'
    assert deep['collection_paused'] and not deep['scientific_approval']
    source_root = Path(deep['root']).resolve()
    assert source_root.name.startswith('scui-deep-') and source_root.is_relative_to(Path(tempfile.gettempdir()).resolve())
    protected = source_files(parent, deep)
    db = source_root / 'data/catalog.db'
    before = snapshot(db)
    cols = before['tables']['collections']['columns']
    assert all(dict(zip(cols, row))['status'] != 'ACTIVE' for row in before['tables']['collections']['rows']), 'Inherited active collections would let a worker claim old tasks; stop without modifying them'
    root = Path(tempfile.mkdtemp(prefix='scui-g11-native-')).resolve()
    exclusive_json(HERE / 'copy-attempt.json', {'root':str(root),'source_root':str(source_root),'status':'STARTED_EXCLUSIVE_COPY'})
    shutil.copytree(source_root / 'data', root / 'data',
                    ignore=lambda _directory, names: [name for name in names if name in {'catalog.db','catalog.db-wal','catalog.db-shm'}])
    target = root / 'data/catalog.db'
    with closing(sqlite3.connect(db.as_uri()+'?mode=ro',uri=True)) as original:
        with closing(sqlite3.connect(target)) as copied:
            original.backup(copied)
    assert snapshot(target) == before, 'Consistent backup must preserve every table and schema exactly'
    for p in (source_root / 'data').rglob('*'):
        if p.is_file() and p.name not in {'catalog.db','catalog.db-wal','catalog.db-shm'}:
            assert digest(root/'data'/p.relative_to(source_root/'data')) == protected[str(p.resolve())]
    import sys
    sys.path.insert(0, str(RSTV4 / 'src'))
    from rstv4.database import CATALOG_VERSION, initialize_catalog
    from rstv4.catalog_web import create_app
    initialize_catalog(target)
    migrated = snapshot(target)
    migration = verify_migration(before, migrated, CATALOG_VERSION)
    app = create_app(root)
    app.state.discussions.gateway = DenyModels()
    app.state.fieldkg_semantics.gateway = DenyModels()
    app.state.discussions.shutdown()
    assert snapshot(target) == migrated, 'App construction must not mutate initialized copied database'
    initialize_catalog(target)
    assert snapshot(target) == migrated, 'Repeated current initialization must be idempotent'
    assert source_files(parent, deep) == protected, 'Original roots/raw files changed during copy/migration'
    exclusive_json(HERE/'copy-before-all-tables.json', before)
    exclusive_json(HERE/'copy-migrated-all-tables.json', migrated)
    receipt = {'status':'PASS_COPY_AND_EXPLICIT_MIGRATION_NOT_NATIVE_ACCEPTANCE', 'root':str(root),
               'db':str(target),'source_root':str(source_root),'port':8887,
               'product_sha256':vector,'protected_original_files':protected,'migration':migration,
               'source_receipt_sha256':{str(parent_path):digest(parent_path),str(deep_path):digest(deep_path)},
               'source_path_policy':'Original stored historical paths preserved; original files read-only. New worker output uses copied AcquisitionService.artifacts_root; no remapping or overwrite of source histories.',
               'original_file_id':parent['file_version_id'],'original_paper_id':parent['paper_id'],
               'original_collection_id':parent['collection_id'],'original_parse':parent['published'],
               'models_executed':0,'workers_started':0,'scientific_approval':False,'native_complete':False}
    exclusive_json(RECEIPT, receipt)
    print(json.dumps({'status':receipt['status'],'root':str(root),'migration':migration}), flush=True)


def serve(port: int) -> None:
    receipt = read_json(RECEIPT)
    root = Path(receipt['root']).resolve()
    assert root.name.startswith('scui-g11-native-') and root.is_relative_to(Path(tempfile.gettempdir()).resolve())
    assert port == 8887 and port not in {3000,3008,8881,8885,8886}
    product_guard(); check_sources(receipt)
    import sys
    sys.path.insert(0,str(RSTV4/'src'))
    import uvicorn
    from rstv4.catalog_web import create_app
    before = snapshot(root/'data/catalog.db')
    app = create_app(root)
    app.state.discussions.gateway = DenyModels()
    app.state.fieldkg_semantics.gateway = DenyModels()
    assert snapshot(root/'data/catalog.db') == before, 'Serve startup changed current copied rows/schema'
    sock = socket.socket()
    sock.bind(('127.0.0.1',port))  # Atomic fresh port ownership; never stop an existing listener.
    sock.listen(128)
    exclusive_json(HERE/'serve-owned-start.json', {'root':str(root),'pid':os.getpid(),'port':port,
                   'status':'SOCKET_BOUND_OWNED_CATALOG_NO_ACQUISITION_WORKER','models_denied':True})
    server = uvicorn.Server(uvicorn.Config(app, log_level='warning'))
    try:
        server.run(sockets=[sock])
    finally:
        sock.close()
        check_sources(receipt)


def main() -> None:
    parser=argparse.ArgumentParser()
    parser.add_argument('mode',choices=['prepare','serve','guard-originals'])
    parser.add_argument('--port',type=int,default=8887)
    args=parser.parse_args()
    if args.mode=='prepare': prepare()
    elif args.mode=='serve': serve(args.port)
    else:
        product_guard(); check_sources(read_json(RECEIPT))
        print('PASS_PREPARED_PRODUCT_AND_ORIGINAL_SOURCE_BYTES',flush=True)


if __name__ == '__main__':
    main()
