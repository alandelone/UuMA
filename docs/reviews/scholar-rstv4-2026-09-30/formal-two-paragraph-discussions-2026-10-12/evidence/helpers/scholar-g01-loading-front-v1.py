from pathlib import Path
source=Path('.tmp/scholar-citation-source-front-v1.py').read_text(encoding='utf-8').replace('scholar-citation-source-front-v1','scholar-g01-loading-front-v1')
exec(compile(source,__file__,'exec'))
