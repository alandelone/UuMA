from pathlib import Path
repo=Path(__file__).resolve().parents[1]
source=(repo/'.tmp/scholar-template-mapping-full-v1.py').read_text(encoding='utf-8')
source=source.replace('scholar-template-mapping-full-v1.','scholar-material-download-full-v1.').replace('scholar-template-mapping-full-inline-v1.','scholar-material-download-full-inline-v1.')
exec(compile(source,__file__,'exec'))
