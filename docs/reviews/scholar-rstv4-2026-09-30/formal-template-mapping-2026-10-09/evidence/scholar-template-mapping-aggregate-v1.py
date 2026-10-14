import json
from pathlib import Path
repo=Path(__file__).resolve().parents[1]
base=json.loads((repo/'.tmp/scholar-template-mapping-preflight-v1.json').read_text(encoding='utf-8'))
receipt=json.loads((repo/'.tmp/scholar-template-mapping-observe-final-compensate-template-v1.json').read_text(encoding='utf-8'))
chain=receipt['operations'];docs={49:base['workspace']['document']}
expected=['ADOPT_TEMPLATE','UNDO','ADOPT_TEMPLATE','PLACE_ORIGINAL_TREE','UNDO','REDO','ADOPT_TEMPLATE','PLACE_ORIGINAL_TREE','UNDO','REDO','UNDO','UNDO']
assert [v['operation']['operation_kind'] for v in chain]==expected
for v in chain:docs[v['operation']['resulting_revision']]=v['after']
for result,prior in [(51,49),(54,52),(55,53),(58,56),(59,57),(60,56),(61,55)]:
    assert docs[result]==docs[prior],(result,prior)
child='section_adf87bef037b4457916e6262e1f4497b'
grand='section_3c2f9eb9623c4896825bf8d11433a036'
section=lambda rev,id:next(s for s in docs[rev]['sections'] if s['id']==id)
assert len(docs[50]['sections'])==len(docs[49]['sections'])+2
for rev in [52,54,56,58,60]:
    assert all(section(rev,id).get('placement_status')=='UNPLACED_ORIGINAL' for id in [child,grand])
for rev in [53,55,57,59,61]:
    assert all(section(rev,id).get('placement_status')!='UNPLACED_ORIGINAL' for id in [child,grand])
    assert section(rev,grand)['parent_section_id']==child
assert section(53,section(53,child)['parent_section_id'])['title']=='Structure Alpha'
assert section(57,section(57,child)['parent_section_id'])['title']=='Structure Beta'
assert docs[61]==docs[55]
assert len(docs[61]['sections'])==5
for name in ['keyboard-cancel','placement-cancel']:
    canceled=json.loads((repo/f'.tmp/scholar-template-mapping-observe-{name}-v1.json').read_text(encoding='utf-8'))
    assert len(canceled['operations'])==canceled['revision']-49
events=json.loads((repo/'.tmp/scholar-template-mapping-native-events-v1.json').read_text(encoding='utf-8'))
print('EVENTS_FORMAT',type(events).__name__)
result={'status':'PASS_EXACT_CASES','revisions':[49,61],'operation_kinds':expected,'exact_full_snapshot_pairs':[[51,49],[54,52],[55,53],[58,56],[59,57],[60,56],[61,55]],'original_tree_target_alpha_then_beta':True,'final_original_objects_restored':True,'cancel_created_no_operation':True,'native_generation_and_model_calls':0,'overall_all11_complete':False}
with (repo/'.tmp/scholar-template-mapping-aggregate-v1.json').open('x',encoding='utf-8') as h:json.dump(result,h,ensure_ascii=False,indent=2)
print(json.dumps(result,ensure_ascii=False))
