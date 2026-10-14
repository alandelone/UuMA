import json
import subprocess
import time
from pathlib import Path

repo = Path(__file__).resolve().parents[1]
python = repo / '.uuma-local/scholar-collection-verification-v1/Scripts/python.exe'
started = time.monotonic()
result = subprocess.run([str(python), '-m', 'pytest', '-q',
                         'tests/test_skeleton_source_outline.py', 'tests/test_studio_templates.py',
                         'tests/test_acquisition_deep_read.py', 'tests/test_parser_quality.py'],
                        cwd=repo.parent / 'RSTV4', capture_output=True, text=True, encoding='utf-8')
(repo / '.tmp/scholar-source-hierarchy-focused-v1.log').write_text(result.stdout + result.stderr, encoding='utf-8')
receipt = {'exit_code': result.returncode, 'seconds': time.monotonic() - started,
           'log': '.tmp/scholar-source-hierarchy-focused-v1.log'}
(repo / '.tmp/scholar-source-hierarchy-focused-v1.json').write_text(json.dumps(receipt, indent=2), encoding='utf-8')
print(result.stdout[-18000:] + result.stderr[-2000:])
print(json.dumps(receipt))
raise SystemExit(result.returncode)
