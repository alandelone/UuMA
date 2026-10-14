from pathlib import Path
code = Path('.tmp/scholar-g03-runtime-refresh-v1.py').read_text(encoding='utf-8').replace('scholar-g03-build-v1', 'scholar-g03-build-v2').replace('scholar-g03-front-v1', 'scholar-g03-front-v3').replace('scholar-g03-runtime', 'scholar-g03-runtime-v2')
code = code.replace('scholar-g02-source-runtime-refresh-v1.json', 'scholar-g03-runtime-refresh-v1.json')
exec(compile(code, __file__, 'exec'))
