from pathlib import Path
source=Path('.tmp/scholar-generated-assets-focused-v8.py').read_text(encoding='utf-8').replace('scholar-generated-assets-focused-v8.','scholar-generated-assets-focused-v9.')
exec(compile(source,__file__,'exec'))
