import hashlib,json,re,subprocess,time,tempfile
from pathlib import Path
repo=Path(__file__).resolve().parents[1]; project=repo.parent/'RSTV4'
python=repo/'.uuma-local/scholar-collection-verification-v1/Scripts/python.exe'
sha=lambda raw:hashlib.sha256(raw).hexdigest()
def snapshot():return {str(p):sha(p.read_bytes()) for base in ['src','tests'] for p in (project/base).rglob('*') if p.is_file() and p.suffix in {'.py','.js','.mjs','.html'}}
before=snapshot();commands=[]
files=['manuscript_scientific_review.py','approval.py','studio.py','catalog_web.py','database.py','models.py','acquisition.py','acquisition_worker.py','collection_web.py','collection_inputs.py','collection_runtime.py','acquisition_model_calls.py','skeleton_audit.py','scope_literature.py','track_first.py','track_scientific_workspace.py','skeleton_intent.py','model_gateway.py','fieldkg_workspace.py','research_views.py']
commands.append([str(python),'-m','ruff','check',*['src/rstv4/'+p for p in files],'tests/test_manuscript_scientific_review.py','tests/test_catalog_paper_selection.py','tests/test_collection_runtime.py','tests/test_acquisition_deep_read.py','tests/test_scope_literature.py','tests/test_track_scientific_workspace.py','tests/test_skeleton_intent.py'])
html=(project/'src/rstv4/catalog_web.html').read_text(encoding='utf-8');scripts=re.findall(r'<script>([\s\S]*?)</script>',html);assert len(scripts)==1
inline=repo/'.tmp/scholar-structured-intent-full-inline-v2.js'
with inline.open('x',encoding='utf-8') as h:h.write(scripts[0])
commands.append(['node','--check',str(inline)])
for name in ['scientific_review','review_workflow','collections','research_workspaces','research_overview']:
 commands.append(['node','tests/catalog_'+name+'.mjs'])
 commands.append(['node','--check','src/rstv4/catalog_'+name+'.js'])
commands.append(['node','tests/catalog_existing_papers.mjs'])
commands.append(['node','tests/catalog_collection_progress.mjs'])
commands.append(['node','tests/catalog_deep_read.mjs'])
commands.append(['node','tests/catalog_scope_literature.mjs'])
commands.append(['node','tests/catalog_track_decisions.mjs'])
commands.append(['node','--check','src/rstv4/catalog_track_decisions.js'])
commands.append(['node','--check','src/rstv4/catalog_collections.js'])
commands.append(['git','diff','--check'])
fixture_base=Path(tempfile.mkdtemp(prefix='scui-full-')).resolve()
assert fixture_base.is_relative_to(Path(tempfile.gettempdir()).resolve()) and fixture_base.name.startswith('scui-full-') and not list(fixture_base.iterdir())
commands.append([str(python),'-X','utf8','-m','pytest','tests','-q','--basetemp',str(fixture_base)])
results=[];started=time.monotonic()
with (repo/'.tmp/scholar-structured-intent-full-v2.log').open('x',encoding='utf-8') as log:
 for command in commands:
  label=' '.join(command[1:]);print('Verify '+label,flush=True);log.write('RUN '+repr(command)+'\n');log.flush()
  result=subprocess.run(command,cwd=project,stdout=log,stderr=subprocess.STDOUT);log.flush()
  results.append({'command':command,'exit_code':result.returncode})
  print('Result '+str(result.returncode),flush=True)
  if result.returncode:break
 after=snapshot();changed=[p for p in before.keys()|after.keys() if before.get(p)!=after.get(p)]
 receipt={'status':'PASS' if all(r['exit_code']==0 for r in results) and len(results)==len(commands) and not changed else 'FAILED','seconds':time.monotonic()-started,'results':results,'before_sha256':before,'after_sha256':after,'changed_during_verification':changed,'log_sha256':sha((repo/'.tmp/scholar-structured-intent-full-v2.log').read_bytes())}
 with (repo/'.tmp/scholar-structured-intent-full-v2.json').open('x',encoding='utf-8') as h:json.dump(receipt,h,indent=2)
 print(json.dumps({k:v for k,v in receipt.items() if k not in {'before_sha256','after_sha256','results'}},ensure_ascii=False),flush=True)
 if receipt['status']!='PASS':raise SystemExit(1)
