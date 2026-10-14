from pathlib import Path
import hashlib
import json
import os
import subprocess

repo = Path(__file__).resolve().parents[1]
front = repo.parent/'writing-studio'
backend = repo.parent/'RSTV4'
python = repo/'.uuma-local/scholar-collection-verification-v1/Scripts/python.exe'
env = {**os.environ, 'PYTHONUTF8': '1', 'NODE_OPTIONS': '--max-old-space-size=512', 'RAYON_NUM_THREADS': '1', 'GOMAXPROCS': '2', 'GOMEMLIMIT': '512MiB'}
checks = [(backend, [str(python), '-m', 'ruff', 'check', 'src/rstv4/studio_correspondence.py',
                    'src/rstv4/studio.py', 'src/rstv4/studio_context.py', 'src/rstv4/studio_structure.py',
                    'src/rstv4/studio_templates.py', 'src/rstv4/studio_read_views.py',
                    'tests/test_studio_correspondence.py', 'tests/test_studio_templates.py']),
          (front, ['node', 'node_modules/typescript/bin/tsc', '--noEmit']),
          (front, [str(front/'node_modules/.bin/oxlint.cmd'), '--type-aware', '--deny-warnings',
                   'lib/studio-correspondence.ts', 'lib/studio-blocks.ts', 'lib/studio-types.ts',
                   'components/studio-intent-correspondence.tsx', 'components/studio-workspace.tsx']),
          (front, ['git', 'diff', '--check'])]
for name in ['studio-correspondence.cjs', 'studio-template-placement.cjs', 'studio-blocks.cjs',
             'studio-block-controls.cjs', 'studio-structure.cjs', 'studio-hierarchy.cjs',
             'studio-undo-history.cjs', 'studio-discussion-history.cjs', 'studio-response-review.cjs',
             'catalog-return.mjs', 'catalog-research-chat.mjs']:
    checks.append((front, ['node', f'tests/unit/{name}']))
results = []
with (repo/'.tmp/scholar-intent-correspondence-static-v4.log').open('x', encoding='utf-8') as log:
    for cwd, command in checks:
        log.write('RUN '+repr(command)+'\n')
        log.flush()
        completed = subprocess.run(command, cwd=cwd, env=env, stdout=log, stderr=subprocess.STDOUT)
        result = {'command': command, 'exit_code': completed.returncode}
        results.append(result)
        print(json.dumps(result), flush=True)
        if completed.returncode:
            break
(repo/'.tmp/scholar-intent-correspondence-static-v4.json').write_text(json.dumps(results, indent=2), encoding='utf-8')
assert len(results) == len(checks) and all(item['exit_code'] == 0 for item in results)
source = (repo/'.tmp/scholar-template-full-v2.py').read_text(encoding='utf-8')
source = source.replace('scholar-template-full-v2.', 'scholar-intent-correspondence-full-v4.').replace(
    'scholar-template-full-inline-v2.', 'scholar-intent-correspondence-full-inline-v4.')
source = source.replace("files=['studio_templates.py'", "files=['studio_correspondence.py','skeleton_outline.py','parser_quality.py','studio_structure.py','studio_context.py','studio_read_views.py','studio_templates.py'")
source = source.replace("'tests/test_studio_templates.py'])", "'tests/test_studio_templates.py','tests/test_studio_correspondence.py','tests/test_studio_hierarchy.py','tests/test_skeleton_source_outline.py','tests/test_fieldkg_semantics.py'])")
exec(compile(source, __file__, 'exec'))
