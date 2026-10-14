import hashlib
import json
import os
import shutil
import subprocess
import tempfile
import time
from pathlib import Path

repo = Path(__file__).resolve().parents[1]
frontend = repo.parent / 'writing-studio'
root = Path(tempfile.mkdtemp(prefix='scui-template-build-'))
sha = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()
excluded = {'node_modules', '.git', '.next', '.vinext', '.runtime', '.wrangler', 'dist', 'test-results', 'coverage'}
def source_snapshot():
    return {str(p.relative_to(frontend)): sha(p) for base in ['app', 'components', 'lib', 'tests', 'dist']
            for p in (frontend / base).rglob('*') if p.is_file()}
before = source_snapshot()
def ignore(directory, names):
    return [name for name in names if name in excluded or name.startswith('.env') or name.endswith(('.log', '.tsbuildinfo'))]
shutil.copytree(frontend, root, dirs_exist_ok=True, ignore=ignore)
assert root.parent == Path(tempfile.gettempdir()) and root.name.startswith('scui-template-build-')
subprocess.run(['powershell', '-NoProfile', '-Command',
    f"New-Item -ItemType Junction -Path '{root / 'node_modules'}' -Target '{frontend / 'node_modules'}' | Out-Null"], check=True)
config = root / 'vite.config.ts'
text = config.read_text(encoding='utf-8')
needle = 'export default defineConfig(() => ({'
assert text.count(needle) == 1
config.write_text(text.replace(needle, needle + "\n    cacheDir: './.isolated-vite-cache',"), encoding='utf-8')
env = os.environ.copy()
env.update(NEXT_PUBLIC_RSTV4_API='http://127.0.0.1:8877/api', NODE_OPTIONS='--max-old-space-size=4096')
receipt = {'root': str(root), 'source': str(frontend), 'before': before, 'api': env['NEXT_PUBLIC_RSTV4_API'],
           'production_original_modified': False, 'started': time.time(), 'status': 'RUNNING'}
path = repo / '.tmp/scholar-template-build-v1.json'
with path.open('x', encoding='utf-8') as handle:
    json.dump(receipt, handle, indent=2)
with (repo / '.tmp/scholar-template-build-v1.log').open('x', encoding='utf-8') as log:
    result = subprocess.run(['cmd.exe', '/c', 'npm.cmd', 'run', 'build'], cwd=root, env=env,
        stdout=log, stderr=subprocess.STDOUT, creationflags=subprocess.CREATE_NO_WINDOW)
after = source_snapshot()
receipt.update(exit_code=result.returncode, seconds=time.time()-receipt['started'],
               original_source_and_dist_unchanged=before == after,
               dist_files={str(p.relative_to(root)): sha(p) for p in (root / 'dist').rglob('*') if p.is_file()},
               status='PASS' if result.returncode == 0 and before == after else 'FAIL')
path.write_text(json.dumps(receipt, indent=2), encoding='utf-8')
print(json.dumps({k:v for k,v in receipt.items() if k not in {'before','dist_files'}}, ensure_ascii=False))
assert receipt['status'] == 'PASS'
