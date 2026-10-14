import json
import os
import subprocess
from pathlib import Path

repo = Path(__file__).resolve().parents[1]
python = repo / '.uuma-local/scholar-collection-verification-v1/Scripts/python.exe'
env = os.environ.copy()
env['PYTHONPATH'] = str(repo.parent / 'RSTV4/src')
cmd = [str(python), '-m', 'pytest', '-q',
       'tests/test_fieldkg_semantics.py::test_schema_upgrade_preserves_all_preexisting_rows_and_stable_reinitialization',
       'tests/test_skeleton_source_outline.py']
result = subprocess.run(cmd, cwd=repo.parent / 'RSTV4', env=env, capture_output=True, text=True, encoding='utf-8')
(repo / '.tmp/scholar-source-hierarchy-schema-focused-v1.log').write_text(result.stdout + result.stderr, encoding='utf-8')
print(result.stdout[-3000:] + result.stderr[-1000:], flush=True)
assert result.returncode == 0
source = (repo / '.tmp/scholar-template-build-v3.py').read_text(encoding='utf-8')
source = source.replace('scholar-template-build-v3.', 'scholar-source-hierarchy-build-v1.').replace(
    'scui-template-build-', 'scui-source-hierarchy-build-').replace('127.0.0.1:8877', '127.0.0.1:8878')
source = source.replace('--max-old-space-size=1536', '--max-old-space-size=512').replace(
    "RAYON_NUM_THREADS='2', UV_THREADPOOL_SIZE='2'", "RAYON_NUM_THREADS='1', UV_THREADPOOL_SIZE='1'")
exec(compile(source, __file__, 'exec'))
for name in ['fixture', 'runtime']:
    command = [str(python), '-X', 'utf8', str(repo / f'.tmp/scholar-source-hierarchy-{name}-v1.py')]
    result = subprocess.run(command, cwd=repo, env=env)
    assert result.returncode == 0, name
print('PASS native fixture and production runtime ready; full regression starts', flush=True)
source = (repo / '.tmp/scholar-template-full-v2.py').read_text(encoding='utf-8')
source = source.replace('scholar-template-full-v2.', 'scholar-source-hierarchy-full-v2.').replace(
    'scholar-template-full-inline-v2.', 'scholar-source-hierarchy-full-inline-v2.')
source = source.replace("files=['studio_templates.py'", "files=['skeleton_outline.py','parser_quality.py','studio_structure.py','studio_context.py','studio_read_views.py','studio_templates.py'")
source = source.replace("'tests/test_studio_templates.py'])", "'tests/test_studio_templates.py','tests/test_studio_hierarchy.py','tests/test_skeleton_source_outline.py','tests/test_fieldkg_semantics.py'])")
exec(compile(source, __file__, 'exec'))
