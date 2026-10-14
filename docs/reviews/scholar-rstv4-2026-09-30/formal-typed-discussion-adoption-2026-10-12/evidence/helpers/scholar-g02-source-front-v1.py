from pathlib import Path
code=Path('.tmp/scholar-citation-source-front-v1.py').read_text(encoding='utf-8').replace('scholar-citation-source-front-v1','scholar-g02-source-front-v1')
exec(compile(code,__file__,'exec'))
