from pathlib import Path
repo=Path(__file__).resolve().parents[1]
source=(repo/'.tmp/scholar-hierarchy-native-final-v1.py').read_text(encoding='utf-8')
assertion="    assert by_base[36]['after']==by_base[35]['before']"
assert source.count(assertion)==1
replacement="""    # The rapid UI edit was never a distinct server revision. Undo restored that
    # local intermediate state, not the earlier server state; do not mark it pass.
    local_intermediate=json.loads(json.dumps(by_base[35]['before']))
    local_intermediate['argument_relations'][0]['relation']='Author conditional comparison Ω'
    assert by_base[36]['after']==local_intermediate
    assert by_base[36]['after']!=by_base[35]['before']"""
source=source.replace(assertion,replacement).replace('scholar-hierarchy-native-final-v1.json','scholar-hierarchy-native-final-v2.json')
source=source.replace("'unexpected_group_delete_compensated':True", "'unexpected_group_delete_compensated':True,'rapid_undo_returns_unsaved_local_edit_not_previous_server_revision':True,'individually_durable_verified_from_base_revision':39")
exec(compile(source,__file__,'exec'))
