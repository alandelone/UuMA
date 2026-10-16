"""v10 contract with the pre-existing v9 path proxy passed through unchanged."""
from pathlib import Path

source = Path(__file__).with_name('runtime_copy_and_serve_v10.py').read_text(encoding='utf-8')
old = 'if Path(candidate).resolve() == path.resolve():'
new = 'if isinstance(candidate, Path) and candidate.resolve() == path.resolve():'
assert source.count(old) == 1
exec(compile(source.replace(old, new), __file__, 'exec'))
