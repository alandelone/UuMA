from pathlib import Path
repo=Path(__file__).resolve().parents[1]
source=(repo/'.tmp/scholar-template-mapping-check-v3.py').read_text(encoding='utf-8')
source=source.replace("'scholar-template-mapping-check-v3.'", "'scholar-template-mapping-check-v5.'")
# Final one-line Chat shortcut guard changes only frontend. The unchanged 69
# backend tests passed in v4; the final full backend run covers them once more.
source=source.replace("source=source.replace(\"'lib/studio-blocks.ts']),\", \"'lib/studio-blocks.ts','lib/studio-undo-history.ts']),\")", "source=source.replace(\"'lib/studio-blocks.ts']),\", \"'lib/studio-blocks.ts','lib/studio-undo-history.ts']),\")\nsource=source.replace('results=[]', 'checks=checks[:-1]\\nresults=[]')")
exec(compile(source,__file__,'exec'))
