"""Preserve the failed old check; prove fixed startup and original records independently."""
import os
import subprocess
import time
from pathlib import Path

import httpx

repo = Path(__file__).resolve().parents[1]
python = str(repo.parent / 'RSTV4/.venv/Scripts/python.exe')
os.environ.update(PYTHONUTF8='1', PYTHONIOENCODING='utf-8')
source = (repo / '.tmp/scholar-discussion-navigation-final-v1.py').read_text(encoding='utf-8')
assert source.count("assert before == prior_final['database_sha256']") == 1
source = source.replace('scholar-discussion-navigation-final-v1.json',
                        'scholar-discussion-navigation-final-v2.json')
source = source.replace(
    "assert before == prior_final['database_sha256'], 'Navigation must preserve the previous database bytes.'",
    """# The retained v1 check failed across the unfixed startup. No original hash is restored.
fixed_baseline = json.loads((repo / '.tmp/scholar-database-startup-fixed-baseline-v1.json').read_text(encoding='utf-8'))
assert before == fixed_baseline['database_sha256'], 'Fixed startup must preserve database bytes.'

def assert_all_original_records():
    with sqlite3.connect(f'{db.as_uri()}?mode=ro', uri=True) as conn:
        tables = [row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")]
        actual = {table: canonical(conn.execute('SELECT * FROM "' + table.replace('"', '""') + '" ORDER BY rowid').fetchall()) for table in tables}
        assert actual == fixed_baseline['all_table_sha256'], 'Every original table must remain unchanged.'
        assert canonical(conn.execute('SELECT * FROM sqlite_master ORDER BY name').fetchall()) == fixed_baseline['schema_sha256']

assert_all_original_records()""")
source = source.replace(
    "assert receipt['job']['status'] == 'COMPLETE'",
    """assert receipt['job']['status'] == 'COMPLETE'
        previous = next(item['body'] for item in prior_final['responses'] if item['method'] == 'GET' and item['path'] == f'/api/research/discussion/requests/{rid}')
        assert receipt == previous, 'The exact original discussion receipt must remain unchanged.'""")
source = source.replace("result['original_database_bytes_unchanged_since_previous_batch'] = True",
    """assert_all_original_records()
result['original_database_bytes_unchanged_since_previous_batch'] = before == prior_final['database_sha256']
result['previous_batch_byte_equality_failed_and_preserved'] = True
result['fixed_startup_all_tables_and_bytes_unchanged'] = True
result['all_tables_verified'] = len(fixed_baseline['all_table_sha256'])
result['exact_previous_discussion_receipts_unchanged'] = True""")
target = repo / '.tmp/scholar-discussion-navigation-final-v2.py'
with target.open('x', encoding='utf-8') as handle:
    handle.write(source)
output = repo / '.tmp/scholar-discussion-navigation-runtime-and-native-v1.log'
with output.open('x', encoding='utf-8') as log:
    for helper in ['scholar-database-startup-fixed-baseline-v1.py',
                   'scholar-discussion-navigation-runtime-v3.py']:
        log.write(f'CHECK {helper}\n')
        log.flush()
        result = subprocess.run([python, str(repo / '.tmp' / helper)], cwd=repo,
                                stdout=log, stderr=subprocess.STDOUT)
        log.write(f'Exit: {result.returncode}\n')
        log.flush()
        if result.returncode:
            print(output.read_text(encoding='utf-8')[-6500:])
            raise SystemExit(result.returncode)
    for attempt in range(40):
        try:
            with httpx.Client(timeout=2) as client:
                assert all(client.get(url).status_code == 200 for url in [
                    'http://127.0.0.1:8885/', 'http://127.0.0.1:8874/api/tracks',
                    'http://127.0.0.1:3000/'])
            break
        except (httpx.HTTPError, AssertionError):
            if attempt == 39:
                raise
            time.sleep(0.5)
    log.write('CHECK scholar-discussion-navigation-final-v2.py\n')
    log.flush()
    result = subprocess.run([python, str(target)], cwd=repo,
                            stdout=log, stderr=subprocess.STDOUT)
    log.write(f'Exit: {result.returncode}\n')
    log.flush()
    print(output.read_text(encoding='utf-8')[-7500:])
    raise SystemExit(result.returncode)
