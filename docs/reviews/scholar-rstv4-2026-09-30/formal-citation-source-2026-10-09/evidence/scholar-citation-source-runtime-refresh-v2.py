from pathlib import Path
source=Path('.tmp/scholar-citation-source-runtime-refresh-v1.py').read_text(encoding='utf-8')
source=source.replace('runtime-refresh-v1','runtime-refresh-v2').replace('backend-runtime-v2','backend-runtime-v3')
source=source.replace("fixture['processes']['backend']",'28468')
exec(compile(source,__file__,'exec'))
