from pathlib import Path
import hashlib
import json
import shutil
import subprocess
import tempfile

root=Path.cwd()
findings=(root/'repomemory/findings.md').read_text(encoding='utf-8')
source=Path('C:/Users/Alandelone/AppData/Local/Temp/pytest-of-Alandelone/pytest-984/test_all_six_original_material0/data/writing-studio')
directories=list(source.glob('*/generated/*'))
assert len(directories)==1
long=directories[0]
short=Path(tempfile.mkdtemp(prefix='sc-tex-probe-')).resolve()
assert short.parent==Path(tempfile.gettempdir()).resolve()
shutil.copytree(long,short,dirs_exist_ok=True)
before={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in long.iterdir() if p.is_file()}
assert all(hashlib.sha256((short/name).read_bytes()).hexdigest()==sha for name,sha in before.items())
cmd=[shutil.which('xelatex'),'-no-shell-escape','-interaction=nonstopmode','-halt-on-error','manuscript.tex']
r=subprocess.run(cmd,cwd=short,capture_output=True,text=True,encoding='utf-8')
(root/'.tmp/scholar-generated-assets-short-path-diagnostic-v1.log').write_text(r.stdout+r.stderr,encoding='utf-8')
after={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in long.iterdir() if p.is_file()}
receipt={'long_directory':str(long),'short_directory':str(short),'longest_input_path':max(len(str(long/name)) for name in before),
         'short_longest_input_path':max(len(str(short/name)) for name in before),
         'all_input_bytes_same':True,'original_files_unchanged':before==after,'short_compile_exit':r.returncode,
         'pdf_exists':(short/'manuscript.pdf').is_file(),'findings_read':len(findings)}
(root/'.tmp/scholar-generated-assets-short-path-diagnostic-v1.json').write_text(json.dumps(receipt,indent=2),encoding='utf-8')
print(json.dumps(receipt))
assert before==after and r.returncode==0
