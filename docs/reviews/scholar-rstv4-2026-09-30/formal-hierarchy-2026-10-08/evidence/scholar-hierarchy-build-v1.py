from pathlib import Path
repo=Path(__file__).resolve().parents[1]
source=(repo/'.tmp/scholar-template-build-v3.py').read_text(encoding='utf-8')
exec(compile(source.replace('scholar-template-build-v3.','scholar-hierarchy-build-v1.').replace('scui-template-build-','scui-hierarchy-build-'),__file__,'exec'))
