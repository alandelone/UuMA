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
here = repo / f'.tmp/scholar-publication-{phase}-v1'
here.mkdir(exist_ok=False)


def files():
    return {p.relative_to(source).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
            for folder in ['src/rstv4', 'tests', 'scripts'] for p in (source / folder).rglob('*')
            if p.is_file() and '__pycache__' not in p.parts and p.suffix != '.pyc'}


before = files()
(here / 'source-before.json').write_text(json.dumps(before, indent=2), encoding='utf-8')
if phase == 'full':
    args = ['tests', '-q']
elif phase == 'before':
    args = ['tests/test_studio_submission_events.py', '-q']
elif phase == 'focused':
    args = ['tests/test_studio_submission_events.py', 'tests/test_writing_studio.py',
            'tests/test_scholar_acceptance_contracts.py', 'tests/test_manuscript_scientific_review.py', '-q']
else:
    raise ValueError(phase)
env = os.environ.copy()
env.update(OMP_NUM_THREADS='1', OPENBLAS_NUM_THREADS='1', MKL_NUM_THREADS='1',
           TOKENIZERS_PARALLELISM='false', PYTHONUTF8='1')
start = time.monotonic()
with (here / 'pytest.log').open('x', encoding='utf-8') as log:
    result = subprocess.run([sys.executable, '-X', 'utf8', '-m', 'pytest', *args],
                            cwd=source, env=env, stdout=log, stderr=subprocess.STDOUT)
assert files() == before, 'Source or tests changed during execution'
receipt = {'status': 'PASS' if result.returncode == 0 else 'FAIL_RETAINED',
           'exit_code': result.returncode, 'seconds': round(time.monotonic() - start, 2),
           'source_files': len(before), 'source_and_tests_unchanged': True,
           'summary': (here / 'pytest.log').read_text(encoding='utf-8')[-3200:],
           'overall11_complete': False}
(here / 'receipt.json').write_text(json.dumps(receipt, ensure_ascii=False, indent=2), encoding='utf-8')
print(json.dumps(receipt, ensure_ascii=False))
raise SystemExit(result.returncode)
