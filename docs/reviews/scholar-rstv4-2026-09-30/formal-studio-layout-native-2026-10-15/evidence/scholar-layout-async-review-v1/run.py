from pathlib import Path
import hashlib
import json
import os
import subprocess
import time

repo = Path.cwd()
folder = repo / '.tmp/scholar-layout-async-review-v1'
candidate = repo / '.tmp/scholar-layout-contract-proposal-v1/candidate/RSTV4'
python = repo / '.uuma-local/scholar-collection-verification-v1/Scripts/python.exe'
attempt = str(time.time_ns())
command = [str(python), '-X', 'utf8', '-m', 'pytest', str(folder / 'test_layout_async.py'), '-k', 'scientific_withdrawal',
           '-q', '--tb=short', f'--basetemp={folder / ("pytest-" + attempt)}']
environment = {**os.environ, 'PYTHONPATH': os.pathsep.join([str(candidate / 'src'), str(candidate / 'tests')]), 'PYTHONIOENCODING': 'utf-8'}
started = time.monotonic()
result = subprocess.run(command, env=environment, capture_output=True, encoding='utf8', errors='replace')
log = folder / f'tests-{attempt}.txt'
log.write_text(result.stdout + '\n' + result.stderr, encoding='utf8')
receipt = {'exit_code': result.returncode, 'seconds': time.monotonic() - started,
           'command': command, 'log': str(log), 'test_sha256': hashlib.sha256((folder / 'test_layout_async.py').read_bytes()).hexdigest(),
           'live_product_modified': False, 'network_models': False, 'test_source_realization': 'one explicit local synthetic gateway call in disposable fixture',
           'replays': 'async real service/compiler, all models denied'}
(folder / f'receipt-{attempt}.json').write_text(json.dumps(receipt, indent=2), encoding='utf8')
print(json.dumps(receipt))
print(result.stdout[-12000:])
print(result.stderr[-2000:])
raise SystemExit(result.returncode)
