import hashlib
import json
import socket
import sqlite3
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path

import uvicorn

repo=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(repo.parent/'RSTV4/tests'))
from test_fieldkg_semantics import setup as make_fixture

root=Path(tempfile.mkdtemp(prefix='scui-semantic-')).resolve()
assert root.is_relative_to(Path(tempfile.gettempdir()).resolve()) and not list(root.iterdir())
test_client,db,field,other,track,build,gateway=make_fixture.__wrapped__(root)
app=test_client.app
sock=socket.socket();sock.bind(('127.0.0.1',0));sock.listen(128)
server=uvicorn.Server(uvicorn.Config(app,log_level='warning'))
thread=threading.Thread(target=server.run,kwargs={'sockets':[sock]},daemon=True);thread.start()
fixture=repo/'.tmp/scholar-fieldkg-semantics-fixture-v1.json'
with fixture.open('x',encoding='utf-8') as handle:
    json.dump({'base':f'http://127.0.0.1:{sock.getsockname()[1]}','root':str(root),'field_id':field,'other_field_id':other,
        'build_id':build,'track_id':track,'source_dir':str(repo.parent/'RSTV4/src/rstv4'),'model_is_explicit_software_fixture':True},handle,indent=2)
with sqlite3.connect(db) as conn:
    original={name:conn.execute('SELECT * FROM '+name+' ORDER BY rowid').fetchall() for name in ['research_nodes','decisions','approval_grants','manuscripts','studio_model_calls']}
try:
    deadline=time.monotonic()+15
    while not server.started and thread.is_alive() and time.monotonic()<deadline:time.sleep(.05)
    assert server.started
    subprocess.run(['node',str(repo/'.tmp/scholar-fieldkg-semantics-native-v1.mjs'),str(fixture),str(repo/'.tmp/scholar-fieldkg-semantics-http-v1.json')],check=True)
    with sqlite3.connect(db) as conn:
        for name,rows in original.items():assert conn.execute('SELECT * FROM '+name+' ORDER BY rowid').fetchall()==rows,name
    proof={'status':'PASS_ACTUAL_HTTP_SEMANTIC_REVIEW_FREEZE_AND_CHAT_SOFTWARE_FIXTURE','root':str(root),
           'gateway_invocations':len(gateway.calls),'model_is_explicit_software_fixture':True,'real_model_calls':0,
           'scientific_tables_unchanged':True,'scientific_approval':False,'browser_verified':False,
           'database_sha256':hashlib.sha256(db.read_bytes()).hexdigest()}
    with (repo/'.tmp/scholar-fieldkg-semantics-native-v1.json').open('x',encoding='utf-8') as handle:json.dump(proof,handle,indent=2)
    print(json.dumps(proof),flush=True)
finally:
    server.should_exit=True;thread.join(10);sock.close()
