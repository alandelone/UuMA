import re
import subprocess
from pathlib import Path

repo = Path(__file__).resolve().parents[1]
project = repo.parent / 'RSTV4'
python = project / '.venv/Scripts/python.exe'
inline = repo / '.tmp/scholar-scope-literature-inline-v1.js'
html = (project / 'src/rstv4/catalog_web.html').read_text(encoding='utf-8')
scripts = re.findall(r'<script>([\s\S]*?)</script>', html)
assert len(scripts) == 1
with inline.open('x', encoding='utf-8') as handle:
    handle.write(scripts[0])
commands = [
    ['node', '--check', str(inline)],
    ['node', 'tests/catalog_research_overview.mjs'],
    ['node', 'tests/catalog_research_workspaces.mjs'],
    [str(python), '-m', 'ruff', 'check', '--fix', 'src/rstv4/scope_literature.py', 'src/rstv4/catalog_web.py', 'tests/test_scope_literature.py'],
    [str(python), '-X', 'utf8', '-m', 'pytest', 'tests/test_scope_literature.py', 'tests/test_research_workspace.py', 'tests/test_fieldkg_workspace.py', '-q'],
]
with (repo / '.tmp/scholar-scope-literature-check-v1.log').open('x', encoding='utf-8') as log:
    for command in commands:
        log.write(repr(command) + '\n')
        log.flush()
        result = subprocess.run(command, cwd=project, stdout=log, stderr=subprocess.STDOUT)
        log.flush()
        print('Result', result.returncode, flush=True)
        if result.returncode:
            raise SystemExit(result.returncode)
