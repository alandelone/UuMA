from pathlib import Path
import hashlib,json,os,subprocess,sys
repo=Path.cwd(); r=repo.parent; out=repo/'.tmp/scholar-citation-source-before-v1';out.mkdir(exist_ok=True)
names=['RSTV4/src/rstv4/studio.py','RSTV4/src/rstv4/studio_api.py','RSTV4/src/rstv4/studio_read_views.py','writing-studio/lib/studio-types.ts','writing-studio/components/studio-workspace.tsx']
hashes={}
for name in names:
 raw=(r/name).read_bytes(); target=out/'before'/name;target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(raw);hashes[name]=hashlib.sha256(raw).hexdigest()
(out/'contract.md').write_text('G05 / G09 source / ST16 / ST28: fixed first-use numeric citation [1],[2],[1]; preserve exact evidence, original raw source unit and surrounding complete parsed source; version-bound PDF must verify exact registered file identity, bytes and digest. Never guess latest source, invent original text or retarget historical references after regeneration. Unknown legacy provenance stays explicit. Fixture is software only; zero scientific approval, no schema transition.\n',encoding='utf-8')
sys.path.insert(0,str(r/'RSTV4/tests'))
from test_studio_source_context import source_studio,generate
import tempfile
fixture=Path(tempfile.mkdtemp(prefix='scui-source-before-'))
service,ms,evidence,source,pdf,document=source_studio(fixture)
before=generate(service,ms)
(out/'before-generated.json').write_text(json.dumps(before,ensure_ascii=False,indent=2),encoding='utf-8')
assert 'source_context' not in before['references'][0]
assert source['file_version_id']=='existing-file' and source['parse_run_id']
service._executor.shutdown(wait=True)
(out/'before.json').write_text(json.dumps({'code_sha256':hashes,'fixture':str(fixture),'manuscript_id':ms,'source_context_missing':True,'has_registered_source_file':True,'has_exact_parse_and_skeleton':True,'software_only':True},indent=2),encoding='utf-8')
with (out/'before-pytest.log').open('x',encoding='utf-8') as log:
 proc=subprocess.run([sys.executable,'-m','pytest','tests/test_studio_source_context.py','-q','--basetemp',str(out/'pytest')],cwd=r/'RSTV4',stdout=log,stderr=subprocess.STDOUT,env={**os.environ,'PYTHONUTF8':'1'})
assert proc.returncode==1,proc.returncode
print(json.dumps({'status':'REPRODUCED_MISSING_SOURCE_CONTEXT','pytest_expected_failure':proc.returncode,'fixture':str(fixture),'code_sha256':hashes}))
print((out/'before-pytest.log').read_text(encoding='utf-8')[-1400:])
