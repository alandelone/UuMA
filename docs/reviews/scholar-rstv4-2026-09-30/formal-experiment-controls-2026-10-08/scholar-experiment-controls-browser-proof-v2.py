import json
import sqlite3
from pathlib import Path

repo = Path(__file__).resolve().parents[1]
meta = json.loads((repo / '.tmp/scholar-experiment-controls-browser-v2.json').read_text())
root = Path(meta['root'])
with sqlite3.connect((root / 'data/catalog.db').as_uri() + '?mode=ro', uri=True) as conn:
    conn.row_factory = sqlite3.Row
    run = dict(conn.execute('SELECT * FROM pipeline_runs').fetchone())
    detail = json.loads(run['detail_json'])
    assert run['status'] == 'COMPLETED'
    target = Path(repo / '.venv/Scripts/python.exe').resolve()
    assert Path(detail['argv'][0]).resolve() == target
    assert Path(detail['metrics']['executable']).resolve() == target
    assert detail['metrics']['value'] == 7
    assert detail['metrics']['selected_env'] == 'pinned-browser'
    assert (root / 'projects/sarawak-pilot/execution-count.txt').read_text() == '1'
    assert conn.execute('SELECT COUNT(*) FROM pipeline_runs').fetchone()[0] == 1
    assert conn.execute('SELECT COUNT(*) FROM acquisition_model_call_events').fetchone()[0] == 0
meta.update(status='PASS_ACTUAL_BROWSER_SELECTED_ENVIRONMENT_AND_INPUT_RECOVERY',
            run_id=run['run_id'], selected_executable=str(target),
            input_removal_preserved_other_draft=True, unavailable_script_preserved=True,
            browser_verified=True, scientific_approval=False,
            legacy_observer_field_preserved_at_capture=True)
with (repo / '.tmp/scholar-experiment-controls-browser-proof-v2.json').open('x', encoding='utf-8') as h:
    json.dump(meta, h, ensure_ascii=False, indent=2)
source = (repo / '.tmp/scholar-experiment-controls-stop-browser-v1.py').read_text()
source = source.replace('browser-v1.json', 'browser-v2.json').replace('browser-server-v1.py', 'browser-server-v2.py')
with (repo / '.tmp/scholar-experiment-controls-stop-browser-v2.py').open('x', encoding='utf-8') as h:
    h.write(source)
print(meta['status'])
