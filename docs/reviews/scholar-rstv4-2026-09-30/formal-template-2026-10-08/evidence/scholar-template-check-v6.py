from pathlib import Path

repo = Path(__file__).resolve().parents[1]
original = (repo / '.tmp/scholar-template-check-v5.py').read_text(encoding='utf-8')
exec(compile(original.replace('scholar-template-check-v5.', 'scholar-template-check-v6.'), __file__, 'exec'))
