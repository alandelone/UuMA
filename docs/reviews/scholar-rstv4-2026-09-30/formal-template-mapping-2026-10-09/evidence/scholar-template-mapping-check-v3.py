from pathlib import Path
repo=Path(__file__).resolve().parents[1]
source=(repo/'.tmp/scholar-template-mapping-check-v1.py').read_text(encoding='utf-8')
source=source.replace('scholar-template-mapping-check-v1.','scholar-template-mapping-check-v3.')
source=source.replace("(front,['node','tests/unit/studio-template-placement.cjs']),", "(front,['node','tests/unit/studio-template-placement.cjs']),(front,['node','tests/unit/studio-undo-history.cjs']),")
source=source.replace("'lib/studio-blocks.ts']),", "'lib/studio-blocks.ts','lib/studio-undo-history.ts']),")
exec(compile(source,__file__,'exec'))
