from pathlib import Path

repo = Path(__file__).resolve().parents[1]
source = (repo / '.tmp/scholar-template-full-v1.py').read_text(encoding='utf-8')
with (repo / '.tmp/scholar-template-full-v2.py').open('x', encoding='utf-8') as handle:
    handle.write(source.replace('scholar-template-full-v1.', 'scholar-template-full-v2.').replace('scholar-template-full-inline-v1.', 'scholar-template-full-inline-v2.'))
