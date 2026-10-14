from pathlib import Path
code=Path('.tmp/scholar-g01-loading-build-v1.py').read_text(encoding='utf-8').replace('scholar-g01-loading-build-v1','scholar-g02-source-build-v1').replace('scui-g01-loading-build-','scui-g02-source-build-')
exec(compile(code,__file__,'exec'))
