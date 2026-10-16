"""Readonly historical v6 origins on preserved r86/v7; all successful work reused."""
from pathlib import Path
repo=Path(__file__).resolve().parents[1]
source=(repo/'.tmp/scholar-frozen-origin-native-v1.py').read_text(encoding='utf8')
source=source[:source.index("if __name__ == '__main__':")]
source=source.replace('scholar-frozen-origin-native-v1','scholar-legacy-origins-native-v1')
source=source.replace("if 'response-review' in path:","if 'response-review' in path or 'response-checks' in path:")
exec(compile(source,__file__,'exec'))
ROUND='review_round_e4845ca796d74594b33b86fb529b4404'

def prepare_legacy():
    HERE.mkdir()
    previous=REPO/'.tmp/scholar-presentation-review-native-v1'
    assert read(previous/'owned-stop-terminal.json')['no_other_processes_stopped']
    r=read(previous/'receipt.json');root=Path(r['root']);before=snap(root/'data/catalog.db')
    assert before==read(previous/'backend-terminal.json')['copy_final_all_tables']
    for n in ['src/rstv4/studio_history_origins.py','tests/test_studio_historical_origins.py']:
        r['backend_source_vector'][n]=sha(RST/n)
    r['backend_source_vector']={n:sha(RST/n) for n in r['backend_source_vector']}
    build=read(REPO/'.tmp/scholar-legacy-origins-build-v1.json');assert build['status']=='PASS'
    with socket.socket() as sock:sock.bind(('127.0.0.1',0));port=sock.getsockname()[1]
    r.update(status='FIXED_OLD_V6_R79_ORIGINS_READONLY_ON_CURRENT_V7_R86',frontend_root=build['root'],frontend_port=port,
        frontend_dist_vector=build['dist_files'],frontend_product_vector={n:sha(REPO.parent/'writing-studio'/n) for n in r['frontend_product_vector']},
        stop_nonce=uuid.uuid4().hex,stop_file=str(HERE/'stop.request.json'))
    guard(r);write('receipt.json',r);write('before110-all-tables.json',before);write('before110-all-files.json',filemap(root))
    write('previous-owned-identity-audit.json',read(previous/'owned-stop-terminal.json'))
    write('reuse-preflight.json',{'A212_old_context_immutable':True,'A215_current_check_retained':True,
        'no_new_model_job_generation_package_or_check':True,'all_mutations_denied':True,'backend318_frontend91_dist_verified':True})
    print(json.dumps({'status':'PREPARED_READONLY_LEGACY_ORIGINS','port':port}),flush=True)

if __name__=='__main__':{'prepare':prepare_legacy,'launch':launch,'serve':serve,'stop':stop}[sys.argv[1]]()
