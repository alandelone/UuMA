from pathlib import Path
import importlib.util,json,hashlib
repo=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('owned_v6',repo/'.tmp/scholar-studio-current-native-restart-v6.py')
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
h=m.HERE;r=m.read(h/'receipt.json');target=m.COMMENT
before=m.read(h/'before110-all-tables.json')
archive=m.read(h/'action-001-all-tables.json');restore=m.read(h/'action-002-all-tables.json')
assert set(before)==set(archive)==set(restore)
for k in before:
    if k!='tables':assert before[k]==archive[k]==restore[k],k
assert set(before['tables'])==set(archive['tables'])==set(restore['tables'])
allowed={'review_comments','studio_comment_response_state'}
assert {t for t in before['tables'] if before['tables'][t]!=archive['tables'][t]}==allowed
assert {t for t in before['tables'] if before['tables'][t]!=restore['tables'][t]}==allowed
def rows(state,table):
    t=state['tables'][table]
    return [dict(zip(t['columns'],row)) for row in t['rows']]
def one(state,table):return next(x for x in rows(state,table) if x['comment_id']==target)
for state in (archive,restore):
    for table in allowed:
        assert [x for x in rows(state,table) if x['comment_id']!=target]==[x for x in rows(before,table) if x['comment_id']!=target]
        assert state['tables'][table]['columns']==before['tables'][table]['columns']
original=one(before,'review_comments');a=one(archive,'review_comments');z=one(restore,'review_comments')
assert original['archived_at'] is None and a['archived_at'] and z['archived_at'] is None
assert {k for k in original if original[k]!=a[k]}=={'archived_at','updated_at'}
assert {k for k in original if original[k]!=z[k]}=={'updated_at'}
assert len(original['response_text'])==554
assert [one(s,'studio_comment_response_state')['revision'] for s in (before,archive,restore)]==[6,7,8]
checks=[x for x in rows(before,'studio_response_checks') if x['comment_id']==target]
links=[x for x in rows(before,'comment_changes') if x['comment_id']==target]
assert len(checks)==2 and len(links)==4
requests=[m.read(p) for p in sorted(h.glob('action-*-request.json'))]
assert len(requests)==2
assert [(x['method'],x['path']) for x in requests]==[('DELETE',f'/api/comments/{target}'),('POST',f'/api/comments/{target}/restore')]
assert all(m.read(p)['status_code']==200 for p in h.glob('action-*-response.json'))
current=m.snapshot(Path(r['root'])/'data/catalog.db')
current['schema']=[list(row) for row in current['schema']]
assert current==restore
del current
m.guard(r)
ui=m.read(repo/'.tmp/scholar-studio-native-actions-v6/native-ui-log.json')
observations={x['label']:x['accessibility']['tree'] for x in ui}
active=observations['a206-active-context-rendered-confirmed']
assert '正在回应' in active and '解除关联 A206' in active
cleared=observations['a206-archived-clears-active-banner-visible']
assert '普通编辑' in cleared and '后续修改不关联审稿意见' in cleared and '解除关联 A206' not in cleared
history=observations['a206-archived-history-full-original-records-loaded']
assert 'dialog A206 的核对历史' in history and history.count('text 作者确认修改')==2
assert original['response_text'] in history
restored=observations['a206-restored-current-card-rendered']
assert '开始修改意见 A206' in restored and original['response_text'] in restored
assert '需要重新核对' in restored and '解除关联 A206' not in restored
out={'status':'PASS_A206_NATIVE_SOFT_ARCHIVE_RESTORE_CURRENT_SOURCE_BOUNDED',
 'comment_id':target,'comment_number':206,'archive_and_restore_native_clicks':True,
 'successful_business_requests':2,'response_revision_sequence':[6,7,8],
 'only_two_tables_changed':sorted(allowed),'other108_tables_exact':True,
 'other_comments_exact':True,'original554_character_reply_exact':True,
 'two_original_checks_and_four_original_links_exact':True,'old_checks_not_reconfirmed':True,
 'active_context_cleared_and_not_auto_restored':True,'manuscript_author_revision62_workflow6_v5_round2_exact':True,
 'source311_frontend91_dist76_original109_external25_exact':True,
 'native_observations':len(ui),'software_fixture_only':True,'scientific_approval':False,
 'overall118_complete':False,'final_all11_integrated_complete':False,
 'no_model_or_gpu_or_generation_execution':True,
 'source_lineage':'same current HTML e573c377 and 310 unchanged backend files; same91 frontend source/76dist'}
m.write('a206-native-audit.json',out)
print(json.dumps(out))
