from pathlib import Path
repo=Path(__file__).resolve().parents[1]
source=(repo/'.tmp/scholar-template-mapping-runtime-before-upgrade-v1.py').read_text(encoding='utf-8')
source=source.replace('scholar-template-mapping-refresh-v1.json','scholar-material-download-refresh-v1.json').replace('scholar-template-mapping-runtime-before-upgrade-v1.json','scholar-material-download-runtime-before-final-v1.json')
exec(compile(source,__file__,'exec'))
