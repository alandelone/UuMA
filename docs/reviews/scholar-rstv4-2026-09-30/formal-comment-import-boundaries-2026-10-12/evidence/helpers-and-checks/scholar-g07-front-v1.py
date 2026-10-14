from pathlib import Path
code=Path('.tmp/scholar-g03-front-v1.py').read_text(encoding='utf-8').replace('scholar-g03-front-v1','scholar-g07-front-v1')
code=code.replace("'app/page.tsx'", "'app/page.tsx','lib/review-comment-preview.ts'")
code=code.replace("['node','tests/unit/studio-view-state.cjs']", "['node','tests/unit/review-comment-preview.cjs'],['node','tests/unit/studio-view-state.cjs']")
exec(compile(code,__file__,'exec'))
