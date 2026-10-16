from pathlib import Path
import hashlib,json
repo=Path(__file__).resolve().parents[1];here=repo/'.tmp/scholar-presentation-review-native-v1'
read=lambda p:json.loads(p.read_text(encoding='utf8'));sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
r=read(here/'receipt.json');terminal=read(here/'backend-terminal.json');mutation=read(here/'declared-mutation-audit.json')
assert terminal['all_other108_tables_exact'] and terminal['all_old_check_rows_exact'] and terminal['all_non_database_bytes_exact']
assert mutation['outcome']=='PRESENTATION_MODIFIED' and mutation['baseline_v6_target_v7']
assert read(here/'owned-stop-terminal.json')['no_other_processes_stopped']
requests=[read(p) for p in here.glob('http-*.json') if not p.name.endswith('-response.json')]
posts=[x for x in requests if x['method']=='POST' and x['path'].endswith('/response-checks')]
assert len(posts)==1 and posts[0]['status']==200
body=posts[0]['request_json'];assert body==read(here/'a215-response-check-request.json')
assert body['outcome']=='PRESENTATION_MODIFIED' and body['acknowledged_all_assertions'] is True
assert len(body['claims'])==1 and body['claims'][0]['start']==24 and body['claims'][0]['end']==126
responses=[read(p) for p in here.glob('http-*-response.json')]
result=next(x for x in responses if 'check_id' in x)
assert not result['idempotent_replay'] and result['check_id']==mutation['new_check_id']
assert result['comment']['status']=='RESOLVED' and result['comment']['response_verification']['status']=='CURRENT'
assert result['comment']['response_verification']['outcome']=='PRESENTATION_MODIFIED' and len(result['history'])==1
check=result['history'][0];ctx=check['context'];row=ctx['evidence'][0]
assert check['request']==body and ctx['baseline_version_number']==6 and ctx['target_version_number']==7
assert not ctx['baseline_to_target_diff'] and ctx['baseline_text_sha256']==ctx['target_text_sha256']
assert row['status']=='LAYOUT_ONLY' and row['change_kind']=='PRESENTATION' and row['supports_scientific_text_modification'] is False
assert row['boxes']!=row['baseline_boxes'] and row['final_pdf_sha256']!=row['baseline_pdf_sha256']
assert row['final_pdf_sha256']=='a78ee2ad02957da5bb56876c4c4c526d7be1fe76359fc0489960b80929634b9b'
assert row['baseline_pdf_sha256']=='ec3988b80410560cd1b40d9bd15615718b2c9ab144147a2d028af461d497c0a1'
history=(here/'native-a215-presentation-history.txt').read_text(encoding='utf8')
assert '作者确认仅排版修改' in history and '仅排版位置变化，正文、引用与素材未变' in history
assert '作者确认不修改及理由' not in history
disabled=(here/'native-scientific-mode-layout-disabled.txt').read_text(encoding='utf8')
assert 'checkbox "声明 1 对应 仅调整成文页边距' in disabled and '[disabled]' in disabled
switched=(here/'native-presentation-switch-clears-claims.txt').read_text(encoding='utf8')
assert 'group "修改声明 1"' not in switched
for n,h in r['backend_source_vector'].items():assert sha(repo.parent/'RSTV4'/n)==h
for n,h in r['frontend_product_vector'].items():assert sha(repo.parent/'writing-studio'/n)==h
audit={'status':'PASS_ONE_NATIVE_A215_TYPED_PRESENTATION_CHECK', 'new_check_id':result['check_id'],
    'outcome':'PRESENTATION_MODIFIED','verification':'CURRENT','comment_status':'RESOLVED','claims_utf16':[[24,126]],
    'one_http_post200_only':True,'fixed_v6_to_v7_actual_pdf_boxes':True,'scientific_MODIFIED_still_rejected':True,
    'all_other108_tables_and_old_checks_exact':True,'all_non_database_files_exact':True,
    'models_jobs_versions_packages_started':0,'backend_source_count':len(r['backend_source_vector']),
    'frontend_source_count':len(r['frontend_product_vector']),'dist_count':len(r['frontend_dist_vector']),
    'old_package_not_rewritten_with_new_acknowledgement':True,'initial_fetch_issue_still_open':True,
    'all_owned_services_stopped':True,'overall118_complete':False,'final11_complete':False}
with (here/'final-audit.json').open('x',encoding='utf8') as f:json.dump(audit,f,indent=2)
print(json.dumps(audit,indent=2))
