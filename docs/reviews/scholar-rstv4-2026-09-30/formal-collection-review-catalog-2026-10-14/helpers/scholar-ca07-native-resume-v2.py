from pathlib import Path
import json

repo = Path.cwd()
out = repo / '.tmp/scholar-ca07-native-v1'
code = Path('.tmp/scholar-ca07-native-v1.py').read_text(encoding='utf-8')
assert code.count('    OUT.mkdir()') == 1
code = code.replace('    OUT.mkdir()', "    assert (OUT / 'allocated.json').exists() and not (OUT / 'prepared.json').exists()")
start = code.index("    root = Path(tempfile.mkdtemp(prefix='scui-ca07-native-')).resolve()")
end = code.index("    sys.path.insert(0, str(REPO.parent / 'RSTV4/src'))", start)
code = code[:start] + '''    root = Path(read_json(OUT / 'allocated.json')['root'])
    assert root.name.startswith('scui-ca07-native-') and root.is_relative_to(Path(tempfile.gettempdir()).resolve())
    target = root / 'data/catalog.db'
    assert read_json(OUT / 'source-before.json') == before
    initialized = snap(target)
''' + code[end:]
code = code.replace('    initialize_catalog(target)\n    after = snap(target)',
                    '    initialize_catalog(target)\n    after = snap(target)\n    assert after == initialized, "Resume must be an idempotent constructor read"')
old = "            assert lookup[key] == [*row[:3], re.sub(uniqueness, '', row[3])]"
new = '''            expected_sql = re.sub(uniqueness, '', row[3]).replace('CREATE TABLE skeleton_runs', 'CREATE TABLE "skeleton_runs"')
            assert lookup[key] == [*row[:3], expected_sql]
        elif row[0] == 'table' and row[1] == 'collections':
            expected_sql = row[3][:-1] + ', topic_id TEXT REFERENCES topics(topic_id), creation_request_json TEXT)'
            assert lookup[key] == [*row[:3], expected_sql]'''
assert code.count(old) == 1
code = code.replace(old, new)
code = code.replace("'only_old_schema_change': 'Documented skeleton history uniqueness removal'",
                    "'old_schema_changes': ['Nullable collections topic_id and creation_request_json additions', 'Skeleton history uniqueness removal and SQLite quoted table name']")
# The long-lived server must execute this explicit resumed contract too.
code = code.replace("str(Path(__file__).resolve()), 'serve'", "str(Path(__file__).resolve()), 'serve'")
context = {'original_failure': 'Read-only migration auditor omitted two actual existing initialize_catalog migrations.',
           'verified_source': 'database.py:1395-1396 adds nullable topic_id/creation_request_json; 1363 SQLite table rename quotes skeleton_runs.',
           'retained_same_allocated_copy': True, 'old_original_fields_and_rows_still_exact': True,
           'source_database_unchanged': True, 'no_native_actions_or_models_replayed': True,
           'resume_initialization_must_be_idempotent': True}
if __name__ == '__main__' and __import__('sys').argv[1] == 'prepare':
    with (out / 'migration-resume-context-v2.json').open('x', encoding='utf-8') as stream:
        json.dump(context, stream, indent=2)
exec(compile(code, __file__, 'exec'))
