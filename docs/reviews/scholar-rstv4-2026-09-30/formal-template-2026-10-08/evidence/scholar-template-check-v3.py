import json
import os
import subprocess
from pathlib import Path

repo = Path(__file__).resolve().parents[1]
project = repo.parent / 'RSTV4'
frontend = repo.parent / 'writing-studio'
python = repo / '.uuma-local/scholar-collection-verification-v1/Scripts/python.exe'
env = os.environ.copy()
env['PYTHONPATH'] = str(project / 'src')
checks = [
    (project, [str(python), '-m', 'ruff', 'check', 'src/rstv4/studio_templates.py', 'src/rstv4/studio.py', 'src/rstv4/studio_api.py', 'tests/test_studio_templates.py']),
    (project, [str(python), '-X', 'utf8', '-m', 'pytest', '-q', 'tests/test_studio_templates.py', 'tests/test_writing_studio.py', 'tests/test_studio_structure.py']),
    (frontend, ['cmd.exe', '/c', 'node_modules\\.bin\\tsc.cmd', '--noEmit']),
    (frontend, ['node', 'tests/unit/studio-structure.cjs']),
    (frontend, ['cmd.exe', '/c', 'node_modules\\.bin\\oxlint.cmd', 'components/studio-template-adoption.tsx', 'components/studio-workspace.tsx', 'lib/studio-api.ts', 'lib/studio-types.ts']),
]
results = []
with (repo / '.tmp/scholar-template-check-v3.log').open('x', encoding='utf-8') as log:
    for cwd, command in checks[2:]:
        print('Verify ' + str(command[1:]), flush=True)
        log.write('RUN ' + repr(command) + '\n'); log.flush()
        result = subprocess.run(command, cwd=cwd, env=env, stdout=log, stderr=subprocess.STDOUT)
        results.append({'command': command, 'exit_code': result.returncode})
        print('Result ' + str(result.returncode), flush=True)
        if result.returncode:
            break
with (repo / '.tmp/scholar-template-check-v3.json').open('x', encoding='utf-8') as handle:
    json.dump(results, handle, indent=2)
if len(results) != len(checks[2:]) or any(r['exit_code'] for r in results):
    raise SystemExit(1)
