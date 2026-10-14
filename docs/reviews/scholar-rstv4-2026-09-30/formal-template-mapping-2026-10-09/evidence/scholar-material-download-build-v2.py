from pathlib import Path
repo=Path(__file__).resolve().parents[1]
source=(repo/'.tmp/scholar-material-download-build-v1.py').read_text(encoding='utf-8')
exec(compile(source.replace('scholar-material-download-build-v1.','scholar-material-download-build-v2.'),__file__,'exec'))
