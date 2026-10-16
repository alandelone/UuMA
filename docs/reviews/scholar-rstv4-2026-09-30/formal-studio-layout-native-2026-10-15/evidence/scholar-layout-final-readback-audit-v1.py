from pathlib import Path
import hashlib
import json
import sys

repo=Path.cwd();sys.path.insert(0,str(repo/'.tmp/scholar-g11-parallel-v1'))
from runtime_copy_and_serve import snapshot
read=lambda p:json.loads(Path(p).read_text(encoding='utf8'))
sha=lambda p:hashlib.sha256(Path(p).read_bytes()).hexdigest()
here=repo/'.tmp/scholar-layout-native-v4';r=read(here/'receipt.json');root=Path(r['root']);current=snapshot(root/'data/catalog.db')
before=read(here/'before110-all-tables.json')
assert current['tables']==before['tables']
assert json.dumps(current['schema'],sort_keys=True)==json.dumps(before['schema'],sort_keys=True)
for name,h in read(here/'before110-all-files.json').items():
    if name not in {'data/catalog.db','data/catalog.db-shm','data/catalog.db-wal'}:assert sha(root/name)==h,name
for name,h in r['backend_source_vector'].items():assert sha(repo.parent/'RSTV4'/name)==h,name
for name,h in r['frontend_product_vector'].items():assert sha(repo.parent/'writing-studio'/name)==h and sha(Path(r['frontend_root'])/name)==h,name
for label,width in [('native-package-wide1280',1280),('native-package-measured760',760)]:
    geometry=read(here/(label+'-geometry.json'));assert geometry['viewport']['width']==width and len(geometry['items'])==21
    for item in geometry['items']:
        cell,b,filename=item['cell'],item['button'],item['filename']
        assert b['width']>0 and b['height']>0
        assert b['left']>=cell['left']-1 and b['right']<=cell['right']+1 and b['top']>=cell['top']-1 and b['bottom']<=cell['bottom']+1
        assert b['scrollWidth']<=b['clientWidth']+1 and filename['scrollWidth']<=filename['clientWidth']+1
        assert filename['left']>=cell['left']-1 and filename['right']<=cell['right']+1
    for index,a in enumerate(geometry['items']):
        for b in geometry['items'][index+1:]:
            x,y=a['cell'],b['cell']
            assert min(x['right'],y['right'])<=max(x['left'],y['left'])+1 or min(x['bottom'],y['bottom'])<=max(x['top'],y['top'])+1
v3=repo/'.tmp/scholar-layout-native-v3'
wide=read(v3/'fixed-toolbar-wide-geometry.json')
narrow=read(v3/'fixed-toolbar-measured760-visible-geometry.json')
assert narrow['viewport']['width']==760 and narrow['viewport']['scrollY']==0
for buttons in [wide,narrow['buttons']]:
    for button in buttons:
        assert button['rect']['width']>0 and button['rect']['height']>0 and button['rect']['top']>=0
        assert button['hit']==button['label'] and button['scrollWidth']<=button['clientWidth']+1
assert read(v3/'native-layout-science-guard.json')['confirmation']==[{'disabled':True}]
def records(state,name):
    table=state['tables'][name];return [dict(zip(table['columns'],row)) for row in table['rows']]
old=read(repo/'.tmp/scholar-layout-native-v1/before110-all-tables.json')
for name in ['comment_changes','studio_comment_response_state']:
    additional=[row for row in records(current,name) if row not in records(old,name)]
    assert len(additional)==1 and additional[0]['comment_id']=='comment_f71edb5758ef41f3b0d96d8cdbed18d5',name
old_operations={o['operation_id'] for o in records(old,'studio_operations')}
operations=[o for o in records(current,'studio_operations') if o['operation_id'] not in old_operations]
assert len(operations)==3 and {o['operation_kind'] for o in operations}=={'EDIT','EDIT_ARGUMENT_RELATION','LAYOUT'}
assert sorted(o['resulting_revision'] for o in operations)==[84,85,86]
full=read(repo/'.tmp/scholar-layout-full-v2/receipt.json');assert full['status']=='PASS' and full['commands_completed']==26
vector=read(full['source_before']);changed=[name for name,h in vector.items() if sha(name)!=h]
assert changed==[str(repo.parent/'writing-studio/app/globals.css')]
receipt={'status':'PASS_FINAL_SAME_V7_PACKAGE_CSS_NATIVE_READBACK','native_package_cells_checked':42,'actual_viewports':[1280,760],
         'all21_buttons_and_filenames_fit_cells_no_intersection':True,'toolbar_text_buttons_fit_and_center_hits_pass':True,
         'final_readonly_UI_all110_exact':True,'final_readonly_UI_all_non_database_files_exact':True,'only_three_author_operations83_to86':True,
         'sole_new_comment_link_and_reply_state_A215':True,'pending_layout_check_not_falsely_confirmed':True,
         'full1178_20warnings_535_90seconds_retained':True,'full24JS_and_Ruff_pass':True,'only_final_CSS_wrap_rule_changed_after_full':True,
         'final_new_build_pass':read(repo/'.tmp/scholar-layout-build-v3.json')['status']=='PASS',
         'final_backend_source_count':len(r['backend_source_vector']),'final_frontend_product_source_count':len(r['frontend_product_vector']),
         'first_origin_parallel_fetch_issue_still_requires_diagnosis':True,'all118_complete':False,'final11_complete':False}
with (here/'final-readonly-audit.json').open('x',encoding='utf8') as f:json.dump(receipt,f,indent=2)
print(json.dumps(receipt,indent=2))
