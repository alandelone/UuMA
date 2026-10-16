"""Preserve v1; admit the actual semantic read-only Catalog query POST."""
from pathlib import Path
import json

parent=Path(__file__).resolve().parents[1]
prior=parent/'.tmp/scholar-quickread-native-preview-v1'
assert json.loads((prior/'owned-stop-terminal.json').read_text(encoding='utf-8'))['status']=='EXACT_OWNED_API_STOPPED_PORT_FREE_ORIGINAL106_FILES311_EXACT'
code=Path(__file__).with_name('scholar-quickread-native-preview-v1.py').read_text(encoding='utf-8')
old="here=repo/'.tmp/scholar-quickread-native-preview-v1'"
assert code.count(old)==1
code=code.replace(old,"here=repo/'.tmp/scholar-quickread-native-preview-v2'")
old="path in {'/api/catalog/discussion/context','/api/catalog/discussion/history'}"
assert code.count(old)==1
code=code.replace(old,"path in {'/api/catalog/discussion/context','/api/catalog/discussion/history','/api/catalog/papers/query'}")
exec(compile(code,__file__,'exec'))
