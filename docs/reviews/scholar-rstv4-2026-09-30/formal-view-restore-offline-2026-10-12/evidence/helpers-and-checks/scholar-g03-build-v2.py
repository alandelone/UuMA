from pathlib import Path
code = Path('.tmp/scholar-g03-build-v1.py').read_text(encoding='utf-8').replace('scholar-g03-build-v1', 'scholar-g03-build-v2')
exec(compile(code, __file__, 'exec'))
