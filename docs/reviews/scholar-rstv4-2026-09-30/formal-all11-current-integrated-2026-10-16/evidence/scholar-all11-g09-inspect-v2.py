import importlib.util
import json
from pathlib import Path
p = Path(__file__).resolve().parent / 'scholar-all11-g09-current-v2.py'
s = importlib.util.spec_from_file_location('g09_current', p)
m = importlib.util.module_from_spec(s)
s.loader.exec_module(m)
receipt, root, context = m.guard()
before = m.read(m.HERE / 'before110.json')
current = m.b.snapshot(root / 'data/catalog.db')
different = {k: {'before': len(before['tables'][k]['rows']), 'now': len(v['rows'])}
             for k, v in current['tables'].items() if v != before['tables'][k]}
old_jobs = {r['job_id'] for r in m.b.records(before, 'studio_jobs')}
jobs = [r for r in m.b.records(current, 'studio_jobs') if r['job_id'] not in old_jobs]
old_packages = {r['package_id'] for r in m.b.records(before, 'studio_submission_packages')}
packages = [r for r in m.b.records(current, 'studio_submission_packages') if r['package_id'] not in old_packages]
assert len(jobs) == len(packages) == 1 and jobs[0]['status'] == 'SUCCEEDED'
print(json.dumps({'different_tables': different, 'new_job': jobs[0], 'new_package': packages[0]}, ensure_ascii=False, indent=2))
m.put(m.HERE / 'package-readonly-inspection.json', {'different_tables': different, 'new_job': jobs[0], 'new_package': packages[0]})
