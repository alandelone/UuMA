from pathlib import Path
repo=Path(__file__).resolve().parents[1]
source=(repo/'.tmp/scholar-hierarchy-startup-v1.py').read_text(encoding='utf-8')
exec(compile(source.replace('scholar-hierarchy-startup-v1.','scholar-hierarchy-startup-v2.'),__file__,'exec'))
