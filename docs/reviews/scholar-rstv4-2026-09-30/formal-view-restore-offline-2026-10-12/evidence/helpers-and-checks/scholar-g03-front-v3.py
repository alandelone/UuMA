from pathlib import Path
code = Path('.tmp/scholar-g03-front-v1.py').read_text(encoding='utf-8').replace('scholar-g03-front-v1', 'scholar-g03-front-v3')
exec(compile(code, __file__, 'exec'))
