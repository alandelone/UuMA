from pathlib import Path
import os,subprocess,json,tempfile,uuid
repo=Path.cwd();backend=repo.parent/'RSTV4';python=repo/'.uuma-local/scholar-collection-verification-v1/Scripts/python.exe'
base=Path(tempfile.gettempdir())/('scsrc-path-'+uuid.uuid4().hex[:8]);assert not base.exists()
args=[str(python),'-m','pytest','tests/test_parser_quality.py::test_mineru_retries_use_fresh_output_directories','tests/test_studio_revision_mapping.py::test_actual_compiled_page_lines_map_multiple_sentences_and_retained_text_separately','tests/test_studio_source_context.py','-q','--basetemp',str(base)]
with (repo/'.tmp/scholar-citation-source-path-contract-v2.log').open('x',encoding='utf-8') as log:r=subprocess.run(args,cwd=backend,env={**os.environ,'PYTHONUTF8':'1'},stdout=log,stderr=subprocess.STDOUT)
(repo/'.tmp/scholar-citation-source-path-contract-v2.json').write_text(json.dumps({'args':args,'exit_code':r.returncode,'short_isolated_base':str(base),'assertions_unchanged':True},indent=2),encoding='utf-8')
print((repo/'.tmp/scholar-citation-source-path-contract-v2.log').read_text(encoding='utf-8')[-4000:]);assert r.returncode==0
