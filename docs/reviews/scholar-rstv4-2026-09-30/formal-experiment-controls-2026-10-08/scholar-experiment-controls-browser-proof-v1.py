import json
import sqlite3
from pathlib import Path

repo = Path(__file__).resolve().parents[1]
m = json.loads((repo / '.tmp/scholar-experiment-controls-browser-v1.json').read_text())
root = Path(m['root'])
c = sqlite3.connect((root / 'data/catalog.db').as_uri() + '?mode=ro', uri=True)
c.row_factory = sqlite3.Row
run = dict(c.execute('select * from pipeline_runs').fetchone())
detail = json.loads(run['detail_json'])
model_tables = [r[0] for r in c.execute("SELECT name FROM sqlite_master WHERE type='table'")
                if 'model_call' in r[0]]
counts = {t: c.execute('select count(*) from "' + t + '"').fetchone()[0]
          for t in ['projects', 'experiment_plans', 'pipeline_runs', 'evidence', *model_tables]}
assert counts['projects'] == 2
assert counts['experiment_plans'] == counts['pipeline_runs'] == counts['evidence'] == 1
assert model_tables and all(counts[t] == 0 for t in model_tables)
assert (root / 'projects/sarawak-pilot/execution-count.txt').read_text() == '1'
assert detail['metrics'] == {'value': 7, 'selected_env': 'reviewed-browser'}
assert len(detail['stdout']) > 2200
assert c.execute("select count(*) from decisions where kind='claim' and status='PROPOSED'").fetchone()[0] == 1
project = dict(c.execute("select * from projects where slug='browser-project'").fetchone())
m.update(browser_workflow_verified=True, run_id=run['run_id'], actual_counts=counts,
         project_metadata=json.loads(project['type_payload_json']), draft_refresh_verified=True,
         claim_remains_proposed=True)
with (repo / '.tmp/scholar-experiment-controls-browser-proof-v1.json').open('x', encoding='utf-8') as h:
    json.dump(m, h, ensure_ascii=False, indent=2)
print(json.dumps({'status': 'PASS_ACTUAL_BROWSER_SOFTWARE_WORKFLOW', 'run': run['status'], 'counts': counts}))
