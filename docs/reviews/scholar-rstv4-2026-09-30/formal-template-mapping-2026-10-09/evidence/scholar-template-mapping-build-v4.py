from pathlib import Path
repo=Path(__file__).resolve().parents[1]
source=(repo/'.tmp/scholar-template-mapping-build-v3.py').read_text(encoding='utf-8')
exec(compile(source.replace('scholar-template-mapping-build-v3.','scholar-template-mapping-build-v4.'),__file__,'exec'))
