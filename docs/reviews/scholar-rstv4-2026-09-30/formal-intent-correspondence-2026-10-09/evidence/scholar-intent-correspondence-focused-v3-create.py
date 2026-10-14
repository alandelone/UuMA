from pathlib import Path
import json
import subprocess
import sys

root=Path.cwd()
runtime=root/'.uuma-local/scholar-collection-verification-v1/Scripts/python.exe'
result=subprocess.run([str(runtime),'-X','utf8','-m','pytest','-q',
    'tests/test_studio_templates.py::test_adoption_record_failure_rolls_back_document_and_operation'],
    cwd=root.parent/'RSTV4',capture_output=True,text=True,encoding='utf-8')
with (root/'.tmp/scholar-intent-correspondence-rollback-narrow-v3.log').open('x',encoding='utf-8') as stream:
    stream.write(result.stdout+'\n'+result.stderr)
print(result.stdout,flush=True)
if result.returncode: raise SystemExit(result.returncode)
original=(root/'.tmp/scholar-intent-correspondence-focused-v2.py').read_text(encoding='utf-8')
successor=original.replace('focused-v2','focused-v3').replace(
    "'RSTV4/tests/test_studio_correspondence.py',", "'RSTV4/tests/test_studio_correspondence.py', 'RSTV4/tests/test_studio_templates.py',")
with (root/'.tmp/scholar-intent-correspondence-focused-v3.py').open('x',encoding='utf-8') as stream:
    stream.write(successor)
print('PASS narrow original rollback guard; successor full relevant checks prepared.')
