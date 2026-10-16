"""One typed A215 acknowledgement; preserve successful generation/package and all old records."""
from pathlib import Path
repo=Path(__file__).resolve().parents[1]
source=(repo/'.tmp/scholar-frozen-origin-native-v1.py').read_text(encoding='utf8')
source=source[:source.index("if __name__ == '__main__':")]
source=source.replace('scholar-frozen-origin-native-v1','scholar-presentation-review-native-v1')
needle="        if not allowed:\n"
assert source.count(needle)==1
insert='''        raw = await request.body()
        if method == 'POST' and path == f'/api/manuscripts/{MS}/comments/comment_f71edb5758ef41f3b0d96d8cdbed18d5/response-checks':
            body = json.loads(raw)
            allowed = body.get('outcome') == 'PRESENTATION_MODIFIED'
            marker = HERE/'a215-response-check-request.json'
            if allowed and marker.exists():
                allowed = read(marker) == body
            elif allowed:
                write(marker.name, body)
'''
source=source.replace(needle,insert+needle)
source=source.replace("'origin':request.headers.get('origin')", "'origin':request.headers.get('origin'),'request_json':json.loads(raw) if raw else None")
source=source.replace("if 'response-review' in path:","if 'response-review' in path or 'response-checks' in path:")
needle="        assert final == baseline, 'Native readonly interval changed table records'"
assert source.count(needle)==1
source=source.replace(needle,"        mutation_audit(baseline, final)")
source=source.replace("omit = {'data/catalog.db-wal','data/catalog.db-shm'}","omit = {'data/catalog.db','data/catalog.db-wal','data/catalog.db-shm'}")
source=source.replace("'all110_exact':True,'all_non_sidecar_bytes_exact':True,","'all_other108_tables_exact':True,'all_old_check_rows_exact':True,'all_non_database_bytes_exact':True,")
source=source.replace("'models_jobs_checks_started':0,","'models_jobs_versions_packages_started':0,'new_A215_check':1,")
exec(compile(source,__file__,'exec'))
ROUND='review_round_72931d507bda4bdb813dc14988444892'

def prepare_presentation():
    HERE.mkdir()
    previous=REPO/'.tmp/scholar-frozen-origin-native-v1'
    assert read(previous/'owned-stop-terminal.json')['no_other_processes_stopped']
    r=read(previous/'receipt.json');root=Path(r['root']);before=snap(root/'data/catalog.db')
    assert before==read(previous/'backend-terminal.json')['copy_final_all_tables']
    c=next(x for x in records(before,'review_comments') if x['comment_id']=='comment_f71edb5758ef41f3b0d96d8cdbed18d5')
    assert c['status']=='PENDING'
    assert not [x for x in records(before,'studio_response_checks') if x['comment_id']==c['comment_id']]
    r['backend_source_vector']['tests/test_studio_presentation_review.py']=sha(RST/'tests/test_studio_presentation_review.py')
    r['backend_source_vector']={n:sha(RST/n) for n in r['backend_source_vector']}
    b=read(REPO/'.tmp/scholar-presentation-review-build-v1.json');assert b['status']=='PASS'
    with socket.socket() as sock:sock.bind(('127.0.0.1',0));port=sock.getsockname()[1]
    r.update(status='ONE_A215_PRESENTATION_CHECK_NO_MODEL_JOB_PACKAGE',frontend_root=b['root'],frontend_port=port,
        frontend_dist_vector=b['dist_files'],frontend_product_vector={n:sha(REPO.parent/'writing-studio'/n) for n in r['frontend_product_vector']},
        stop_nonce=uuid.uuid4().hex,stop_file=str(HERE/'stop.request.json'))
    guard(r);write('receipt.json',r);write('before110-all-tables.json',before);write('before110-all-files.json',filemap(root))
    write('previous-owned-identity-audit.json',read(previous/'owned-stop-terminal.json'))
    write('reuse-preflight.json',{'same_v7_r86_and_package_preserved':True,'one_A215_check_only':True,
        'all_jobs_models_author_operations_denied':True,'old_nochange_scientific_checks_immutable':True})
    print(json.dumps({'status':'PREPARED_A215_TYPED_PRESENTATION','port':port}),flush=True)

def mutation_audit(before,after):
    assert before['schema']==after['schema'] and set(before['tables'])==set(after['tables']) and len(before['tables'])==110
    changed={n for n in before['tables'] if before['tables'][n]!=after['tables'][n]}
    assert changed=={'review_comments','studio_response_checks'},changed
    old={x['comment_id']:x for x in records(before,'review_comments')}
    new={x['comment_id']:x for x in records(after,'review_comments')}
    assert old.keys()==new.keys()
    cid='comment_f71edb5758ef41f3b0d96d8cdbed18d5'
    assert all(old[k]==new[k] for k in old if k!=cid)
    assert old[cid]['status']=='PENDING' and new[cid]['status']=='RESOLVED'
    assert {k for k in old[cid] if old[cid][k]!=new[cid][k]}=={'status','updated_at'}
    old_checks={x['check_id']:x for x in records(before,'studio_response_checks')}
    new_checks={x['check_id']:x for x in records(after,'studio_response_checks')}
    assert len(new_checks)==len(old_checks)+1 and all(new_checks[k]==v for k,v in old_checks.items())
    check=next(v for k,v in new_checks.items() if k not in old_checks)
    assert check['comment_id']==cid and check['outcome']=='PRESENTATION_MODIFIED'
    body=read(HERE/'a215-response-check-request.json')
    assert json.loads(check['request_json'])=={'manuscript_id':MS,'comment_id':cid,**body}
    context=json.loads(check['context_json']);assert context['target_version_number']==7 and context['baseline_version_number']==6
    assert not context['baseline_to_target_diff'] and not context['scientific_acceptance']
    assert body['claims'][0]['start']==24 and body['claims'][0]['end']==126
    write('declared-mutation-audit.json',{'changed_tables':sorted(changed),'other108_exact':True,
        'only_A215_status_updated_at_changed':True,'all_old_checks_exact':True,'new_check_id':check['check_id'],
        'outcome':'PRESENTATION_MODIFIED','exact_request_saved':True,'baseline_v6_target_v7':True,'scientific_approval':False})

if __name__=='__main__':{'prepare':prepare_presentation,'launch':launch,'serve':serve,'stop':stop}[sys.argv[1]]()
