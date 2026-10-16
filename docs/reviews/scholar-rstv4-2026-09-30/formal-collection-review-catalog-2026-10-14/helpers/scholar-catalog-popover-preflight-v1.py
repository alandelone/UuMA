from pathlib import Path
import json
import sys

repo = Path.cwd()
sys.path.insert(0,str(repo / '.tmp/scholar-g11-parallel-v1'))
from runtime_copy_and_serve_v9 import fixture_vector_unchanged_except_declared_popover, read_json
receipt = read_json(repo / '.tmp/scholar-ca07-native-v1/prepared.json')
current = fixture_vector_unchanged_except_declared_popover(receipt['source_vector'])
with (repo / '.tmp/scholar-catalog-popover-fix-v1/source-preflight.json').open('x',encoding='utf-8') as stream:
    json.dump({'status':'PASS_EXACT_POPUP_REVERSAL_AND_ALL_PREVIOUS_GUARDS','vector':current},stream,indent=2)
print('PASS_EXACT_POPUP_REVERSAL_AND_ALL_PREVIOUS_GUARDS')
