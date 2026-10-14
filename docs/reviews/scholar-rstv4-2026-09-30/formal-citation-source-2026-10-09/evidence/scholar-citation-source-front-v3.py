from pathlib import Path
source=Path('.tmp/scholar-citation-source-front-v1.py').read_text(encoding='utf-8').replace('front-v1','front-v3')
exec(compile(source,__file__,'exec'))
