from pathlib import Path
import hashlib
import json
import os
import subprocess
import time

root = Path.cwd()
backend = root.parent / 'RSTV4'
frontend = root.parent / 'writing-studio'
python = root / '.uuma-local/scholar-collection-verification-v1/Scripts/python.exe'
checks = [
    ('pytest', backend, [str(python), '-X', 'utf8', '-m', 'pytest', '-q',
                        'tests/test_studio_correspondence.py', 'tests/test_studio_templates.py',
                        'tests/test_skeleton_source_outline.py', 'tests/test_studio_hierarchy.py',
                        'tests/test_studio_context.py']),
    ('correspondence-unit', frontend, ['node', 'tests/unit/studio-correspondence.cjs']),
    ('placement-unit', frontend, ['node', 'tests/unit/studio-template-placement.cjs']),
    ('blocks-unit', frontend, ['node', 'tests/unit/studio-blocks.cjs']),
    ('tsc', frontend, ['node', 'node_modules/typescript/bin/tsc', '--noEmit']),
    ('oxlint', frontend, [str(frontend/'node_modules/.bin/oxlint.cmd'), '--type-aware', '--deny-warnings',
                         'lib/studio-correspondence.ts', 'lib/studio-blocks.ts', 'lib/studio-types.ts',
                         'components/studio-intent-correspondence.tsx', 'components/studio-workspace.tsx']),
]
files = ['RSTV4/src/rstv4/studio.py', 'RSTV4/src/rstv4/studio_context.py',
         'RSTV4/src/rstv4/studio_structure.py', 'RSTV4/src/rstv4/studio_templates.py',
         'RSTV4/src/rstv4/studio_correspondence.py', 'RSTV4/tests/test_studio_correspondence.py', 'RSTV4/tests/test_studio_templates.py',
         'writing-studio/lib/studio-correspondence.ts', 'writing-studio/lib/studio-blocks.ts',
         'writing-studio/lib/studio-types.ts', 'writing-studio/components/studio-workspace.tsx',
         'writing-studio/components/studio-intent-correspondence.tsx',
         'writing-studio/tests/unit/studio-correspondence.cjs']
hashes = {name: hashlib.sha256((root.parent/name).read_bytes()).hexdigest() for name in files}
results = []
env = {**os.environ, 'PYTHONUTF8': '1', 'PYTHONDONTWRITEBYTECODE': '1', 'NODE_OPTIONS': '--max-old-space-size=512', 'RAYON_NUM_THREADS': '1'}
start = time.monotonic()
with (root/'.tmp/scholar-intent-correspondence-focused-v3.log').open('x', encoding='utf-8') as log:
    for name, cwd, argv in checks:
        result = subprocess.run(argv, cwd=cwd, capture_output=True, text=True, encoding='utf-8', env=env)
        log.write(f'CHECK {name} exit={result.returncode}\n{result.stdout}\n{result.stderr}\n')
        log.flush()
        results.append({'check': name, 'exit_code': result.returncode})
        print(json.dumps(results[-1]), flush=True)
after = {name: hashlib.sha256((root.parent/name).read_bytes()).hexdigest() for name in files}
assert after == hashes
data = {'status': 'PASS' if all(item['exit_code']==0 for item in results) else 'FAIL',
        'checks': results, 'seconds': round(time.monotonic()-start,3), 'source_sha256': hashes,
        'source_unchanged_while_running': True}
(root/'.tmp/scholar-intent-correspondence-focused-v3.json').write_text(json.dumps(data,indent=2),encoding='utf-8')
print(json.dumps({k:v for k,v in data.items() if k!='source_sha256'}))
raise SystemExit(0 if data['status']=='PASS' else 1)
