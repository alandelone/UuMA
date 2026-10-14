from pathlib import Path

repo = Path(__file__).resolve().parents[1]
note = '''

## 2026-10-08 Studio template lint execution context

Template check v2 passed45 backend tests and TypeScript but rejected3 new status elements;
semantic output tags corrected. Check v3 retained type/control passes but the unchanged
type-aware Go checker failed VirtualAlloc errno1455 / out of memory. Preserve v2/v3 logs;
no rule disabled, no source assertion weakened. Run the same selected files and full
configured type-aware/type-check rules with oxlint --threads=1, GOMAXPROCS=2 and
GOMEMLIMIT=512MiB, then source-stable full regression. Keep original golden build untouched;
use a separate copied frontend tree for production build. The attempted inline context
writer failed shell parsing before any write; subsequent missing v4 helper is not lint evidence.
Use materialized helper files for these multi-line updates.
'''
for name in ['repomemory/findings.md', 'rules/scholar-native-acceptance.md']:
    path = repo / name
    assert 'Studio template lint execution context' not in path.read_text(encoding='utf-8')
    with path.open('a', encoding='utf-8') as handle:
        handle.write(note)
source = (repo / '.tmp/scholar-template-check-v3.py').read_text(encoding='utf-8')
source = source.replace('scholar-template-check-v3', 'scholar-template-check-v4')
source = source.replace("env['PYTHONPATH'] = str(project / 'src')",
                        "env['PYTHONPATH'] = str(project / 'src')\nenv.update(GOMAXPROCS='2', GOMEMLIMIT='512MiB')")
source = source.replace("'components/studio-template-adoption.tsx'", "'--threads=1', 'components/studio-template-adoption.tsx'")
source = source.replace('checks[2:]', 'checks[4:]')
with (repo / '.tmp/scholar-template-check-v4.py').open('x', encoding='utf-8') as handle:
    handle.write(source)
