from pathlib import Path
repo=Path(__file__).resolve().parents[1]
source=(repo/'.tmp/scholar-template-mapping-full-v1.py').read_text(encoding='utf-8')
exec(compile(source.replace('scholar-template-mapping-full-v1.','scholar-template-mapping-full-v2.').replace('scholar-template-mapping-full-inline-v1.','scholar-template-mapping-full-inline-v2.'),__file__,'exec'))
