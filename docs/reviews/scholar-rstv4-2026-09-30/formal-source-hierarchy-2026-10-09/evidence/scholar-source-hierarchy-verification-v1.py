from pathlib import Path
import json
import os
import subprocess

repo = Path(__file__).resolve().parents[1]
front = repo.parent / 'writing-studio'
env = os.environ.copy()
env.update(NODE_OPTIONS='--max-old-space-size=512', GOMAXPROCS='2', GOMEMLIMIT='512MiB')
checks = [['cmd.exe', '/c', 'node_modules\\.bin\\tsc.cmd', '--noEmit'],
          ['cmd.exe', '/c', 'node_modules\\.bin\\oxlint.cmd', '--threads=1',
           'components/studio-template-adoption.tsx', 'lib/studio-types.ts'], ['git', 'diff', '--check']]
results = []
with (repo / '.tmp/scholar-source-hierarchy-static-v1.log').open('x', encoding='utf-8') as log:
    for command in checks:
        result = subprocess.run(command, cwd=front, env=env, stdout=log, stderr=subprocess.STDOUT)
        results.append({'command': command, 'exit_code': result.returncode})
        print('Frontend check ' + str(len(results)) + ': ' + str(result.returncode), flush=True)
        if result.returncode:
            break
(repo / '.tmp/scholar-source-hierarchy-static-v1.json').write_text(json.dumps(results, indent=2), encoding='utf-8')
assert len(results) == len(checks) and all(r['exit_code'] == 0 for r in results)
source = (repo / '.tmp/scholar-template-full-v2.py').read_text(encoding='utf-8')
source = source.replace('scholar-template-full-v2.', 'scholar-source-hierarchy-full-v1.').replace(
    'scholar-template-full-inline-v2.', 'scholar-source-hierarchy-full-inline-v1.')
source = source.replace("files=['studio_templates.py'", "files=['skeleton_outline.py','parser_quality.py','studio_structure.py','studio_context.py','studio_read_views.py','studio_templates.py'")
source = source.replace("'tests/test_studio_templates.py'])", "'tests/test_studio_templates.py','tests/test_studio_hierarchy.py','tests/test_skeleton_source_outline.py'])")
exec(compile(source, __file__, 'exec'))
source = (repo / '.tmp/scholar-template-build-v3.py').read_text(encoding='utf-8')
source = source.replace('scholar-template-build-v3.', 'scholar-source-hierarchy-build-v1.').replace(
    'scui-template-build-', 'scui-source-hierarchy-build-').replace('127.0.0.1:8877', '127.0.0.1:8878')
source = source.replace('--max-old-space-size=1536', '--max-old-space-size=512').replace(
    "RAYON_NUM_THREADS='2', UV_THREADPOOL_SIZE='2'", "RAYON_NUM_THREADS='1', UV_THREADPOOL_SIZE='1'")
exec(compile(source, __file__, 'exec'))
