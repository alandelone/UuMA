import json
from pathlib import Path
import httpx
repo=Path(__file__).resolve().parents[1]
fixture=json.loads((repo/'.tmp/scholar-template-native-fixture-v1.json').read_text(encoding='utf-8'))
response=httpx.get(f"http://127.0.0.1:8877/api/manuscripts/{fixture['native_manuscript_id']}/workspace",timeout=12);response.raise_for_status()
assert response.json()['document_revision']==55
result={'status':'FAILED_NATIVE_REFRESH_UNDO_BEFORE_FIX','expected_revision':56,'actual_revision':55,
        'cause':'undoRef/redoRef initialized to empty arrays on reload; button was enabled but returned without mutation',
        'failed_command':'.tmp/scholar-template-mapping-observe-v1.py refresh-undo-attempt 56',
        'original_database_untouched':True,'failed_assertion_preserved':True,'workspace':response.json()}
with (repo/'.tmp/scholar-template-mapping-refresh-undo-diagnostic-v1.json').open('x',encoding='utf-8') as h:json.dump(result,h,indent=2,ensure_ascii=False)
print(result['status'])
