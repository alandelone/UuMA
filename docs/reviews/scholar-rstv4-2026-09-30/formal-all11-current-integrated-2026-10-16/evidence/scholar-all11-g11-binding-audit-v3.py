"""Read-only independent JSON-contract audit; frozen preparation helper unchanged."""
from pathlib import Path
import runpy,json
repo=Path(__file__).resolve().parents[1]
m=runpy.run_path(str(repo/'.tmp/scholar-all11-g11-current-v2.py'),run_name='frozen_prepare_readonly')
read=m['read'];here=m['HERE'];receipt=read(here/'receipt.json');m['guard_originals'](receipt)
bindings={}
canonical=lambda x:json.dumps(x,ensure_ascii=False,sort_keys=True,separators=(',',':'))
for role,entry in receipt['copies'].items():
    root=Path(entry['root']);current=m['snapshot'](root/'data/catalog.db')
    assert current==read(here/f'{role}-baseline110.json')
    assert m['filemap'](root)==read(here/f'{role}-baseline-files.json')
    value=m['binding'](role,current,root);saved=read(here/f'{role}-binding.json')
    assert canonical(value)==canonical(saved)
    if role=='upstream':
        assert isinstance(value['stale_claim_ids'],tuple) and isinstance(saved['stale_claim_ids'],list)
        assert list(value['stale_claim_ids'])==saved['stale_claim_ids']
        assert {k:v for k,v in value.items() if k!='stale_claim_ids'}=={k:v for k,v in saved.items() if k!='stale_claim_ids'}
    else:assert value==saved
    bindings[role]=saved
m['guard_originals'](receipt)
m['put']('readonly-binding-audit-v3.json',{'status':'PASS_CURRENT421_THREE_COMPATIBLE_COPIES_AND_FROZEN_ORIGINALS',
    'source421':receipt['source421'],'bindings':bindings,'all_original_and_copied_tables_schema_files_exact':True,
    'original_v2_helper_and_receipt_SHA_unchanged':True,'upstream_tuple_to_JSON_array_contract_only_correction':True,
    'new_model_job_gpu_quickread_approval_or_business_action':0,'current_native_and_guard_acceptance_complete':False})
print('PASS_ALL_FIELDS_JSON_BINDINGS_AND_ALL_TABLES_FILES_FROZEN_NATIVE_GUARDS_REMAIN')
