from pathlib import Path

repo = Path(__file__).resolve().parents[1]
source = (repo / '.tmp/scholar-revision-full-v1.py').read_text(encoding='utf-8')
source = source.replace('scholar-revision-full', 'scholar-template-full')
source = source.replace('import hashlib,json,re,subprocess,time,tempfile', 'import hashlib,json,re,subprocess,time,tempfile,os')
source = source.replace("sha=lambda raw:hashlib.sha256(raw).hexdigest()", "sha=lambda raw:hashlib.sha256(raw).hexdigest()\nenv=os.environ.copy();env.update(PYTHONPATH=str(project/'src'),GOMAXPROCS='2',GOMEMLIMIT='512MiB')\nfrontend=repo.parent/'writing-studio'")
old = "def snapshot():return {str(p):sha(p.read_bytes()) for base in ['src','tests'] for p in (project/base).rglob('*') if p.is_file() and p.suffix in {'.py','.js','.mjs','.html'}}"
new = """def snapshot():
 return {str(p):sha(p.read_bytes()) for root,bases in [(project,['src','tests']),(frontend,['app','components','lib','tests'])] for base in bases for p in (root/base).rglob('*') if p.is_file() and p.suffix in {'.py','.js','.mjs','.cjs','.html','.ts','.tsx','.css'}}"""
assert old in source
source = source.replace(old, new)
source = source.replace("files=['manuscript_scientific_review.py'", "files=['studio_templates.py','studio_api.py','manuscript_scientific_review.py'")
source = source.replace("'tests/test_experiment_workspace.py'])", "'tests/test_experiment_workspace.py','tests/test_studio_templates.py'])")
source = source.replace("result=subprocess.run(command,cwd=project,stdout=log,stderr=subprocess.STDOUT)", "result=subprocess.run(command,cwd=project,env=env,stdout=log,stderr=subprocess.STDOUT)")
with (repo / '.tmp/scholar-template-full-v1.py').open('x', encoding='utf-8') as handle:
    handle.write(source)
