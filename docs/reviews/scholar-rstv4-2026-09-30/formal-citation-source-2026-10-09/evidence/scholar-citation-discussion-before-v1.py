from pathlib import Path
import os,subprocess,json,tempfile,uuid,hashlib
repo=Path.cwd(); backend=repo.parent/'RSTV4'; folder=repo/'.tmp/scholar-citation-discussion-before-v1';folder.mkdir()
source=backend/'src/rstv4/studio_discussions.py'; (folder/'studio_discussions.py').write_bytes(source.read_bytes())
base=Path(tempfile.gettempdir())/('scdis-before-'+uuid.uuid4().hex[:8]);assert not base.exists()
with (folder/'test.log').open('x',encoding='utf-8') as log:
 r=subprocess.run([str(repo/'.uuma-local/scholar-collection-verification-v1/Scripts/python.exe'),'-m','pytest','tests/test_studio_discussion_fixed_references.py','-q','--basetemp',str(base)],cwd=backend,env={**os.environ,'PYTHONUTF8':'1'},stdout=log,stderr=subprocess.STDOUT)
text=(folder/'test.log').read_text(encoding='utf-8');print(text[-7000:])
(folder/'receipt.json').write_text(json.dumps({'exit_code':r.returncode,'original_source_sha256':hashlib.sha256(source.read_bytes()).hexdigest(),'basetemp':str(base)},indent=2),encoding='utf-8')
assert r.returncode==1 and '3 failed, 2 passed' in text
