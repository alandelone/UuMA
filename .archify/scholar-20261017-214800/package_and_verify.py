from pathlib import Path
import hashlib
import json
import zipfile
ROOT=Path(__file__).resolve().parents[2]
BASE=Path(__file__).resolve().parent
rows=[('architecture','scholar-architecture','review-3'),('workflow','scholar-workflow',''),('sequence','scholar-sequence','review-3'),('dataflow','scholar-dataflow','review-3'),('class','scholar-code','')]
verified=[]
for mode,name,review in rows:
    receipt_path=BASE/mode/review/(name+'.finalize-summary.json')
    receipt=json.loads(receipt_path.read_text(encoding='utf-8'))
    assert receipt['ok'] and receipt['status']=='pass', mode
    assert all(receipt['gates'][g]=='pass' for g in ['validate','deliver','check','browser-check']), mode
    for key in ['artifact','specification']:
        record=receipt[key]
        file=Path(record['path'])
        assert hashlib.sha256(file.read_bytes()).hexdigest()==record['sha256'], (mode,key)
    verified.append({'type':mode,'status':'pass','gates':receipt['gates'],'artifact':str((BASE/mode/(name+'.html')).relative_to(BASE)).replace('\\','/'),'receipt':str(receipt_path.relative_to(BASE)).replace('\\','/'),'visual_review':'not-requested','layout_advice':receipt.get('visualReviewRecommendation'),'update':receipt.get('update')})
summary={'repository':'https://github.com/alandelone/UuMA.git','revision':'0e273c8dce5f846dd1ffebd78e0d9e60ce8d3319','verified_diagrams':verified,'source_scope':'UuMA implementation; RSTV4 internals are external documented contracts.','product_source_modified':False,'service_runtime_verified':False}
(BASE/'verification.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding='utf-8')
archive=BASE/'scholar-diagrams.zip'
with zipfile.ZipFile(archive,'w',compression=zipfile.ZIP_DEFLATED,compresslevel=9) as z:
    for file in ['index.html','README.md','verification.json']:
        z.write(BASE/file,file)
    for mode,name,review in rows:
        for file in [name+'.html','candidate.json']:
            z.write(BASE/mode/file,mode+'/'+file)
        z.write(BASE/mode/review/(name+'.finalize-summary.json'),'evidence/'+mode+'.finalize-summary.json')
with zipfile.ZipFile(archive) as z:
    assert z.testzip() is None
    assert len(z.namelist())==18
    for mode,name,_ in rows:
        assert z.read(mode+'/'+name+'.html')==(BASE/mode/(name+'.html')).read_bytes()
print(json.dumps({'ok':True,'diagrams':len(verified),'all_four_gates':'pass','archive':str(archive),'archive_bytes':archive.stat().st_size,'archive_sha256':hashlib.sha256(archive.read_bytes()).hexdigest()},ensure_ascii=False))
