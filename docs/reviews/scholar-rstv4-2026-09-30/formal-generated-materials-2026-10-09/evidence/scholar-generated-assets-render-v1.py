from pathlib import Path
import hashlib
import json
import shutil
import subprocess

root=Path.cwd()
focused=json.loads((root/'.tmp/scholar-generated-assets-focused-v5.json').read_text(encoding='utf-8'))
assert focused['status']=='PASS' and len(focused['material_receipts'])==1
receipt=json.loads(Path(focused['material_receipts'][0]).read_text(encoding='utf-8'))
pdf=Path(receipt['pdf'])
before=hashlib.sha256(pdf.read_bytes()).hexdigest()
output=root/'.tmp/scholar-generated-assets-render-v1'
output.mkdir()
render=shutil.which('pdftoppm')
assert render
result=subprocess.run([render,'-png','-r','110',str(pdf),str(output/'page')],capture_output=True,text=True,check=False)
assert result.returncode==0,result.stderr
pages=sorted(output.glob('page-*.png'))
assert pages and hashlib.sha256(pdf.read_bytes()).hexdigest()==before
(output/'render-record.json').write_text(json.dumps({'pdf':str(pdf),'sha256':before,
    'renderer':render,'pages':[str(p) for p in pages],'read_only':True,'scientific_acceptance':False},indent=2),encoding='utf-8')
print(json.dumps({'pages':[str(p) for p in pages],'pdf':str(pdf),'sha256':before}))
