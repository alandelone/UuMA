from pathlib import Path
import hashlib
import json
import os
import subprocess
import sys
import time

repo = Path(__file__).resolve().parents[1]
source = repo.parent / 'RSTV4'
phase = sys.argv[1]
here = repo / f'.tmp/scholar-reader-{phase}-v1'
here.mkdir(exist_ok=False)


def files():
    return {p.relative_to(source).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
            for folder in ['src/rstv4', 'tests', 'scripts'] for p in (source / folder).rglob('*')
            if p.is_file() and '__pycache__' not in p.parts and p.suffix != '.pyc'}


before = files()
(here / 'source-before.json').write_text(json.dumps(before, indent=2), encoding='utf-8')
env = os.environ.copy()
env.update(OMP_NUM_THREADS='1', OPENBLAS_NUM_THREADS='1', MKL_NUM_THREADS='1',
           TOKENIZERS_PARALLELISM='false', PYTHONUTF8='1')
if phase == 'full':
    commands = [('pytest', [sys.executable, '-X', 'utf8', '-m', 'pytest', 'tests', '-q'])]
elif phase == 'frontend':
    commands = [(p.stem, ['node', str(p)]) for p in sorted((source / 'tests').glob('catalog*.mjs'))]
    commands.append(('ruff', [sys.executable, '-m', 'ruff', 'check',
                             'src/rstv4/catalog_annotations.py', 'src/rstv4/catalog_web.py',
                             'tests/test_catalog_annotation_retries.py']))
else:
    raise ValueError(phase)
results = []
for name, command in commands:
    start = time.monotonic()
    with (here / f'{name}.log').open('x', encoding='utf-8') as log:
        result = subprocess.run(command, cwd=source, env=env, stdout=log, stderr=subprocess.STDOUT)
    results.append({'name': name, 'exit_code': result.returncode,
                    'seconds': round(time.monotonic() - start, 2)})
assert files() == before, 'Source or tests changed during execution'
receipt = {'status': 'PASS' if all(x['exit_code'] == 0 for x in results) else 'FAIL_RETAINED',
           'checks': results, 'source_files': len(before), 'source_and_tests_unchanged': True,
           'native_browser_executed': False, 'overall11_complete': False}
if phase == 'full':
    receipt['summary'] = (here / 'pytest.log').read_text(encoding='utf-8')[-3200:]
(here / 'receipt.json').write_text(json.dumps(receipt, ensure_ascii=False, indent=2), encoding='utf-8')
print(json.dumps(receipt, ensure_ascii=False))
raise SystemExit(0 if receipt['status'] == 'PASS' else 1)
