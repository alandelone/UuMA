from pathlib import Path
code=Path('.tmp/scholar-g03-build-v1.py').read_text(encoding='utf-8').replace('scholar-g03-build-v1','scholar-g07-build-v1').replace('scui-g03-build-','scui-g07-build-')
exec(compile(code,__file__,'exec'))
