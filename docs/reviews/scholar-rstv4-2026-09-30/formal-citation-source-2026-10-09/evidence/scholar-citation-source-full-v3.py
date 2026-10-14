from pathlib import Path
repo=Path.cwd()
source=(repo/'.tmp/scholar-citation-source-full-v1.py').read_text(encoding='utf-8').replace('full-v1','full-v3')
source=source.replace('import hashlib,json,os,subprocess,time','import hashlib,json,os,subprocess,time,tempfile,uuid')
source=source.replace('before=source_snapshot(); results=[];start=time.time()',"base=Path(tempfile.gettempdir())/('scsrc-full-'+uuid.uuid4().hex[:8]);assert not base.exists()\nbefore=source_snapshot(); results=[];start=time.time()")
source=source.replace("str(repo/'.tmp/scholar-citation-source-full-v3-pytest')",'str(base)')
source=source.replace("'tests/test_studio_source_context.py']","'tests/test_studio_source_context.py','src/rstv4/studio_discussions.py','tests/test_studio_discussion_fixed_references.py']")
assert '--basetemp\',str(base)' in source and 'test_studio_discussion_fixed_references.py' in source
exec(compile(source,__file__,'exec'))
