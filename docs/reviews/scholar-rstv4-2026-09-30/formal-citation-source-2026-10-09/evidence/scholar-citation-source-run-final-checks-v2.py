from pathlib import Path
repo=Path.cwd()
front=(repo/'.tmp/scholar-citation-source-front-v1.py').read_text(encoding='utf-8').replace('front-v1','front-v2')
exec(compile(front,__file__,'exec'))
source=(repo/'.tmp/scholar-citation-source-full-v1.py').read_text(encoding='utf-8').replace('full-v1','full-v2')
source=source.replace('import hashlib,json,os,subprocess,time','import hashlib,json,os,subprocess,time,tempfile,uuid')
source=source.replace('before=source_snapshot(); results=[];start=time.time()',"base=Path(tempfile.gettempdir())/('scsrc-full-'+uuid.uuid4().hex[:8]);assert not base.exists()\nbefore=source_snapshot(); results=[];start=time.time()")
source=source.replace("str(repo/'.tmp/scholar-citation-source-full-v2-pytest')",'str(base)')
assert '--basetemp\',str(base)' in source
exec(compile(source,__file__,'exec'))
