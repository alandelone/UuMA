import json
import subprocess
import zipfile
from pathlib import Path

repo = Path(__file__).resolve().parents[1]
out = repo / '.tmp/scholar-fieldkg-semantics-wheel-v1'
out.mkdir(exist_ok=False)
command = [str(repo / '.uuma-local/scholar-collection-verification-v1/Scripts/python.exe'), '-m', 'pip',
           'wheel', '--no-deps', '--no-build-isolation', '--disable-pip-version-check', '--wheel-dir', str(out),
           str(repo.parent / 'RSTV4')]
with (repo / '.tmp/scholar-fieldkg-semantics-packaging-v1.log').open('x', encoding='utf-8') as log:
    result = subprocess.run(command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, encoding='utf-8', errors='replace')
    log.write(result.stdout);print(result.stdout, flush=True)
    if result.returncode:raise SystemExit(result.returncode)
wheels = list(out.glob('*.whl'));assert len(wheels) == 1
required = ['catalog_web.html','catalog_research_overview.js','catalog_research_chat.js',
            'catalog_research_workspaces.js','catalog_collections.js','catalog_review_workflow.js','catalog_scientific_review.js','collection_runtime.py','acquisition.py','acquisition_worker.py','models.py','database.py','collection_web.py','acquisition_model_calls.py','skeleton_audit.py','catalog_web.py','scope_literature.py','track_first.py','track_scientific_workspace.py','catalog_track_decisions.js','model_gateway.py','skeleton_intent.py','fieldkg_workspace.py','research_views.py','durable_model_delivery.py','fieldkg_semantics.py','research_context.py']
with zipfile.ZipFile(wheels[0]) as wheel:
    for name in required:
        assert wheel.read('rstv4/' + name) == (repo.parent / 'RSTV4/src/rstv4' / name).read_bytes()
with (repo / '.tmp/scholar-fieldkg-semantics-packaging-v1.json').open('x', encoding='utf-8') as handle:
    json.dump({'status':'PASS_ALL_EIGHT_SHIPPED_CATALOG_ASSETS', 'assets':required,'wheel':str(wheels[0])},handle,indent=2)
print('Actual distribution includes the exact Catalog HTML and all seven shipped JavaScript files.')
