from pathlib import Path
import json
repo=Path.cwd()
source=(repo/'.tmp/scholar-citation-source-seal-v1.py').read_text(encoding='utf-8')
source=source.replace("delta=[name for name,digest in full['after'].items()", "delta=[Path(name).as_posix() for name,digest in full['after'].items()")
assert 'delta=[Path(name).as_posix()' in source
(repo/'.tmp/scholar-citation-source-seal-execution-context-v1.json').write_text(json.dumps({'prior_seal_preflight':'FAILED_BEFORE_REPORT_CREATION','reason':'Windows source snapshot uses backslash separators; canonical path equality requires Path.as_posix before the same exact one-file assertion.','allowed_post_full_source_delta':'writing-studio/components/studio-workspace.tsx','test_or_product_assertions_changed':False,'lifecycle_projection_error':'An intermittent Invalid argument on active-session/progress.md occurred after the command event was persisted; lifecycle engine is not modified.'},indent=2),encoding='utf-8')
exec(compile(source,__file__,'exec'))
