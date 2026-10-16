from pathlib import Path

path = Path(__file__).resolve()
source = path.with_name('scholar-reader-http-v1.py').read_text(encoding='utf-8')
source = source.replace('req.method', 'req.get_method()')
source = source.replace('.tmp/scholar-reader-http-v1', '.tmp/scholar-reader-http-v2')
exec(compile(source, __file__, 'exec'))
