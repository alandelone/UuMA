from pathlib import Path
import json
import os
import psutil
import socket
import subprocess
import sys
import time
import urllib.request
repo=Path(__file__).resolve().parents[1]
here=repo/'.tmp/scholar-g11-parallel-v1/gpu-health-retry-context-v1'
assert not (here/'launched-read-v2.json').exists()
result=json.loads((here.parent/'actual-mineru-gpu-health-retry-v1/actual-mineru-once-result.json').read_text())
assert result['execution']['status']=='SUCCEEDED' and result['execution']['attempts']==6
sys.path.insert(0,str(here.parent))
from runtime_copy_and_serve_v8 import product_guard,snapshot
product_guard();db=Path(result['root'])/'data/catalog.db';before=snapshot(db)
root=psutil.Process(json.loads((here/'launched.json').read_text())['pid'])
children=root.children(recursive=True)
owned=[]
for p in [root]+children:
    if p.name().lower()=='conhost.exe':
        assert p.ppid()==root.pid and Path(p.exe()).resolve()==Path(os.environ['SystemRoot']).resolve()/'System32/conhost.exe'
        continue
    assert p.name().lower()=='python.exe' and any('scholar-g11-gpu-healthy-serve-v1.py' in x for x in p.cmdline())
    assert Path(p.cwd()).resolve()==repo
    owned.append({'pid':p.pid,'created':p.create_time(),'argv':p.cmdline()})
listener=[c for c in psutil.net_connections(kind='tcp') if c.status=='LISTEN' and c.laddr.port==8887]
assert len(listener)==1 and listener[0].pid in {x['pid'] for x in owned}
(here/'read-refresh-owned-targets-v2.json').open('x',encoding='utf-8').write(json.dumps(owned,indent=2))
for row in reversed(owned):
    try:
        p=psutil.Process(row['pid']);assert p.create_time()==row['created'] and p.cmdline()==row['argv']
        p.terminate();p.wait(timeout=4)
    except psutil.NoSuchProcess:pass
with socket.socket() as probe:probe.bind(('127.0.0.1',8887))
argv=[str(repo/'.uuma-local/scholar-collection-verification-v1/Scripts/python.exe'),'-X','utf8',str(repo/'.tmp/scholar-g11-gpu-success-read-serve-v2.py')]
with (here/'read-v2-stdout.log').open('xb') as out,(here/'read-v2-stderr.log').open('xb') as err:
    p=subprocess.Popen(argv,cwd=repo,env=os.environ.copy(),stdin=subprocess.DEVNULL,stdout=out,stderr=err,creationflags=subprocess.CREATE_NO_WINDOW)
(here/'launched-read-v2.json').open('x',encoding='utf-8').write(json.dumps({'pid':p.pid,'argv':argv,'port':8887,'retry_already_consumed':True,'only_added_semantic_read':'POST /api/catalog/papers/query'},indent=2))
end=time.monotonic()+25
while True:
    try:
        with urllib.request.urlopen('http://127.0.0.1:8887/',timeout=2) as r:assert r.status==200
        break
    except Exception:
        assert time.monotonic()<end,'Inspect exact new child; do not relaunch'
        time.sleep(.2)
assert snapshot(db)==before
(here/'read-ready-v2.json').open('x',encoding='utf-8').write(json.dumps({'status':'PASS_READ_QUERY_ENABLED_NO_DB_CHANGE','pid':p.pid,'retry_consumed':True}))
print('PASS owned read-only catalog query enabled; successful parse/DB unchanged; retry consumed')
