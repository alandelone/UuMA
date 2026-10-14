from pathlib import Path
import hashlib
import json
import os
import psutil
import socket
import subprocess
import time
import urllib.request

repo=Path(__file__).resolve().parents[1]
here=repo/'.tmp/scholar-native-import-v1/comments-read-recovery-v1'
assert not (here/'replaced-frontend-v2.json').exists()
old=json.loads((repo/'.tmp/scholar-native-import-build-v1.json').read_text())
new=json.loads((repo/'.tmp/scholar-native-import-build-v2.json').read_text())
launch=json.loads((repo/'.tmp/scholar-native-import-v1/launched-v1.json').read_text())
assert new['status']=='PASS' and new['original_source_and_dist_unchanged']
front=Path(new['root'])
for name,sha in new['dist_files'].items():
    assert hashlib.sha256((front/name).read_bytes()).hexdigest()==sha
for name,sha in new['before'].items():
    assert hashlib.sha256((Path(new['source'])/name).read_bytes()).hexdigest()==sha
listeners={c.laddr.port:c.pid for c in psutil.net_connections(kind='tcp') if c.status=='LISTEN' and c.laddr.port in {3009,8889}}
assert set(listeners)=={3009,8889}
backend_pid=listeners[8889]
backend=psutil.Process(backend_pid)
backend_identity=(backend.create_time(),backend.cmdline())
root=psutil.Process(next(x['pid'] for x in launch['processes'] if x['name']=='frontend'))
children=root.children(recursive=True)
assert listeners[3009] in [p.pid for p in children]+[root.pid]
listener=psutil.Process(listeners[3009])
assert listener.name().lower()=='node.exe'
assert any(old['root'] in x for x in listener.cmdline())
assert '3009' in listener.cmdline() and '--port' in listener.cmdline()
assert Path(listener.cwd()).resolve()==Path(old['root']).resolve()
targets=[{'pid':p.pid,'created':p.create_time(),'argv':p.cmdline(),'cwd':p.cwd()} for p in list(reversed(children))+[root]]
(here/'frontend-v1-verified-retirement-targets.json').open('x',encoding='utf-8').write(json.dumps(targets,indent=2))
for item in targets:
    try:
        p=psutil.Process(item['pid'])
        assert p.create_time()==item['created'] and p.cmdline()==item['argv']
        p.terminate()
        p.wait(timeout=4)
    except psutil.NoSuchProcess:
        pass
with socket.socket() as probe:probe.bind(('127.0.0.1',3009))
assert backend.is_running() and (backend.create_time(),backend.cmdline())==backend_identity
env=os.environ.copy()
env.update(RSTV4_API='http://127.0.0.1:8889/api',NODE_OPTIONS='--max-old-space-size=512')
argv=['cmd.exe','/c','npm.cmd','run','start','--','--port','3009','--hostname','127.0.0.1']
with (here/'frontend-v2-stdout.log').open('xb') as out,(here/'frontend-v2-stderr.log').open('xb') as err:
    proc=subprocess.Popen(argv,cwd=front,env=env,stdin=subprocess.DEVNULL,stdout=out,stderr=err,creationflags=subprocess.CREATE_NO_WINDOW)
receipt={'status':'STARTED_OWNED_FRONTEND_V2','pid':proc.pid,'created':psutil.Process(proc.pid).create_time(),'argv':argv,'cwd':str(front),'old_owned_processes':targets,'unchanged_backend_pid':backend_pid,'files_deleted':0}
(here/'replaced-frontend-v2.json').open('x',encoding='utf-8').write(json.dumps(receipt,indent=2))
end=time.monotonic()+25
while True:
    try:
        with urllib.request.urlopen('http://127.0.0.1:3009/',timeout=2) as r:assert r.status==200
        break
    except Exception:
        assert time.monotonic()<end,'Inspect startup, do not relaunch'
        time.sleep(.2)
assert backend.is_running() and (backend.create_time(),backend.cmdline())==backend_identity
(here/'frontend-v2-ready.json').open('x',encoding='utf-8').write(json.dumps({'status':'PASS','pid':proc.pid,'backend_pid_unchanged':backend_pid}))
print(json.dumps({'status':'PASS_OWNED_FRONTEND_UPDATED_API_UNCHANGED','pid':proc.pid,'backend_pid':backend_pid,'ports':[3009,8889],'files_deleted':0}))
