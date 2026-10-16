from pathlib import Path
import json, os, subprocess, time

repo = Path(__file__).resolve().parents[1]
here = repo / '.tmp/scholar-frozen-origin-v1'
python = repo / '.uuma-local/scholar-collection-verification-v1/Scripts/python.exe'
rst = repo.parent / 'RSTV4'
front = repo.parent / 'writing-studio'
commands = [([str(python), '-X', 'utf8', '-m', 'pytest', 'tests/test_studio_frozen_origins.py',
              'tests/test_studio_revision_mapping.py', 'tests/test_studio_response_checks.py',
              'tests/test_studio_response_citation_display.py', '-q', '--tb=short'], rst),
            (['node', 'tests/unit/studio-response-review.cjs'], front),
            (['node', 'node_modules/typescript/bin/tsc', '--noEmit'], front),
            ([str(python), '-m', 'ruff', 'check', 'src/rstv4/studio_revision_mapping.py', 'tests/test_studio_frozen_origins.py'], rst)]
env = {**os.environ, 'PYTHONPATH': str(rst / 'src'), 'PYTHONIOENCODING': 'utf-8'}
results = []
for i, (command, cwd) in enumerate(commands):
    start = time.monotonic()
    log = here / f'focused-v2-{i}.log'
    with log.open('x', encoding='utf8') as output:
        result = subprocess.run(command, cwd=cwd, env=env, stdout=output, stderr=subprocess.STDOUT, check=False, creationflags=subprocess.CREATE_NO_WINDOW)
    row = {'command': command, 'cwd': str(cwd), 'exit_code': result.returncode, 'seconds': time.monotonic()-start, 'log': str(log)}
    results.append(row)
    print(json.dumps(row), flush=True)
(here / 'focused-v2-receipt.json').write_text(json.dumps(results, indent=2), encoding='utf8')
assert all(x['exit_code'] == 0 for x in results)
