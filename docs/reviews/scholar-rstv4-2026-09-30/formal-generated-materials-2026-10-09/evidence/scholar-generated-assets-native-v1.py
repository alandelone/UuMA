from pathlib import Path
from copy import deepcopy
import hashlib
import json
import os
import shutil
import socket
import sqlite3
import subprocess
import sys
import tempfile
import time

repo=Path(__file__).resolve().parents[1]
receipt_path=repo/'.tmp/scholar-generated-assets-native-v1.json'
if len(sys.argv)>1:
    import uvicorn
    from fastapi.middleware.cors import CORSMiddleware
    from rstv4.studio_api import create_app
    fixture=json.loads(receipt_path.read_text(encoding='utf-8'))
    app=create_app(fixture['root'])
    app.add_middleware(CORSMiddleware,allow_origins=['http://127.0.0.1:3007'],allow_methods=['*'],allow_headers=['*'])
    def software_realization(task,payload):
        assert task=='paragraph_realization'
        thoughts=[t for i in payload['intents'] for t in i['thoughts']]
        return {'paragraph':' '.join(t['text'] for t in thoughts),
                'sentence_mappings':[{'sentence':0,'thought_ids':[t['id'] for t in thoughts]}],
                '_contract':{'actual_model':'TEST_FIXTURE_MATERIALS_NATIVE','task':task}}
    app.state.studio.gateway.analyze=software_realization
    uvicorn.run(app,host='127.0.0.1',port=8880,log_level='warning')
    raise SystemExit()
for port in [3007,8880]:
    with socket.socket() as handle: assert handle.connect_ex(('127.0.0.1',port))!=0
parent=json.loads((repo/'.tmp/scholar-intent-correspondence-native-v1.json').read_text(encoding='utf-8'))
source_root=Path(parent['root']).resolve()
assert source_root.name.startswith('scui-intent-correspondence-native-')
root=Path(tempfile.mkdtemp(prefix='scui-generated-materials-native-')).resolve()
assert root.parent==Path(tempfile.gettempdir()).resolve()
shutil.copytree(source_root,root,dirs_exist_ok=True,
                ignore=lambda directory,names:[n for n in names if n.startswith('catalog.db')])
db=root/'data/catalog.db'
def snapshot(path):
    with sqlite3.connect(f'file:{path.as_posix()}?mode=ro',uri=True) as conn:
        conn.row_factory=sqlite3.Row
        return {r[0]:[dict(v) for v in conn.execute(f'SELECT * FROM "{r[0]}" ORDER BY rowid')]
                for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")}
before=snapshot(source_root/'data/catalog.db')
assert len(before)==109
with sqlite3.connect(f'file:{(source_root/"data/catalog.db").as_posix()}?mode=ro',uri=True) as old:
    with sqlite3.connect(db) as target: old.backup(target)
sys.path.insert(0,str(repo.parent/'RSTV4/tests'))
from test_writing_studio import complete_document
from test_studio_generated_assets import six_materials
from rstv4.studio import StudioService
from rstv4.models import FieldInput,TrackFirstTopicInput,TrackFirstTrackInput
service=StudioService(root)
field=service.track_service.create_field(FieldInput(name='Six-material software Field '+root.name))
topic=service.track_service.create_topic(TrackFirstTopicInput(field_id=field['field_id'],name='Six-material software Topic '+root.name))
track=service.track_service.create_track(TrackFirstTrackInput(field_id=field['field_id'],
    primary_topic_id=topic['topic_id'],title='Six-material software Track',research_type='conceptual_framework'))['track_id']
ms=service.create_manuscript(track,'Six-material software manuscript')['manuscript']['manuscript_id']
doc=complete_document(service.get_workspace(ms))
doc['title']='Six original material formats - software acceptance'
doc['sections'][0]['title']='Original materials'
paragraph=doc['sections'][0]['paragraphs'][0]
paragraph['purpose']='Present all original software fixtures without rewriting their data'
paragraph['paradigm']='Author-defined original material sequence'
paragraph['intents'][0]['label']='Original fixture placement'
paragraph['intents'][0]['thoughts'][0]['text']='These six original software fixtures test material delivery only. No scientific result is asserted.'
assets,files=six_materials(service,ms)
paragraph['asset_ids']=[a['asset_id'] for a in assets]
service.save_document(ms,base_revision=0,operation_id='native-six-original-materials',document=doc)
after=snapshot(db)
assert before.keys()==after.keys()
for table,records in before.items():
    assert all(record in after[table] for record in records),table
assert before['studio_model_calls']==after['studio_model_calls']
assert before['approval_grants']==after['approval_grants']
service._executor.shutdown(wait=True)
receipt={'root':str(root),'manuscript_id':ms,'track_id':track,'initial_document':doc,
         'assets':assets,'before_tables':before,'after_fixture_tables':after,
         'schema_version':13,'table_count':109,'prior_rows_unchanged':True,
         'software_fixture':True,'actual_remote_model_calls':0,'scientific_acceptance':False,
         'download_testing_resumed':True,'file_upload_test_authorization_not_expanded':True}
with receipt_path.open('x',encoding='utf-8') as handle: json.dump(receipt,handle,ensure_ascii=False,indent=2)
source=(repo/'.tmp/scholar-template-build-v3.py').read_text(encoding='utf-8')
source=source.replace('scholar-template-build-v3.','scholar-generated-assets-build-v1.').replace(
    'scui-template-build-','scui-generated-materials-build-').replace('127.0.0.1:8877','127.0.0.1:8880')
source=source.replace('--max-old-space-size=1536','--max-old-space-size=512').replace(
    "RAYON_NUM_THREADS='2', UV_THREADPOOL_SIZE='2'","RAYON_NUM_THREADS='1', UV_THREADPOOL_SIZE='1'")
exec(compile(source,str(repo/'.tmp/scholar-template-build-v3.py'),'exec'),{'__file__':str(repo/'.tmp/scholar-template-build-v3.py')})
build=json.loads((repo/'.tmp/scholar-generated-assets-build-v1.json').read_text(encoding='utf-8'))
assert build['status']=='PASS'
processes={}
env={**os.environ,'PYTHONPATH':str(repo.parent/'RSTV4/src'),'PYTHONUTF8':'1',
     'NODE_OPTIONS':'--max-old-space-size=512','RAYON_NUM_THREADS':'1','UV_THREADPOOL_SIZE':'1'}
for name,command,cwd in [
    ('backend',[sys.executable,str(Path(__file__).resolve()),'serve'],repo),
    ('frontend',['cmd.exe','/c','npm.cmd','run','start','--','--port','3007','--hostname','127.0.0.1'],Path(build['root']))]:
    with (repo/f'.tmp/scholar-generated-assets-{name}-runtime-v1.log').open('x',encoding='utf-8') as log:
        process=subprocess.Popen(command,cwd=cwd,env=env,stdout=log,stderr=subprocess.STDOUT,creationflags=subprocess.CREATE_NO_WINDOW)
    processes[name]=process.pid
import httpx
ready=set()
with httpx.Client(timeout=3) as client:
    deadline=time.monotonic()+45
    while len(ready)<2 and time.monotonic()<deadline:
        for name,url in [('backend',f'http://127.0.0.1:8880/api/manuscripts/{ms}/workspace'),('frontend','http://127.0.0.1:3007/')]:
            if name in ready:continue
            try:
                if client.get(url).status_code==200:ready.add(name)
            except httpx.HTTPError:pass
        if len(ready)<2:time.sleep(.3)
receipt.update(production_root=build['root'],processes=processes,ready=sorted(ready),
               url=f'http://127.0.0.1:3007/?manuscript={ms}&view=structure&left=1&right=1&chat=0')
receipt_path.write_text(json.dumps(receipt,ensure_ascii=False,indent=2),encoding='utf-8')
assert ready=={'backend','frontend'}
print(json.dumps({k:receipt[k] for k in ['root','manuscript_id','production_root','processes','ready','url','prior_rows_unchanged']}))
