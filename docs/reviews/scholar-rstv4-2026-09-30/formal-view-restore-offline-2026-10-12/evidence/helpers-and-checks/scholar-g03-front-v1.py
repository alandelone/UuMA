from pathlib import Path
code = Path('.tmp/scholar-citation-source-front-v1.py').read_text(encoding='utf-8').replace('scholar-citation-source-front-v1', 'scholar-g03-front-v1')
code = code.replace("'lib/studio-types.ts'", "'app/page.tsx','lib/studio-view-state.ts','lib/studio-types.ts'")
code = code.replace("['node','tests/unit/studio-downloads.cjs']", "['node','tests/unit/studio-view-state.cjs'],['node','tests/unit/studio-downloads.cjs']")
exec(compile(code, __file__, 'exec'))
