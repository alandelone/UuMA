from pathlib import Path
import hashlib,json,socket,sys,time,psutil
REPO=Path(__file__).resolve().parents[1]
OLD=REPO/'.tmp/scholar-studio-current-native-v2'
HERE=REPO/'.tmp/scholar-studio-current-native-restart-v9'
read=lambda p:json.loads(p.read_text(encoding='utf8'))
r=read(HERE/'receipt.json');owned=read(HERE/'ownership.json')
def exact(saved):
 try:p=psutil.Process(saved['pid'])
 except psutil.NoSuchProcess:return None
 assert p.create_time()==saved['create_time'] and p.cmdline()==saved['cmdline'] and p.cwd()==saved['cwd'],'PID identity changed; do not stop'
 return p
backend=exact(owned['backend']);front=exact(owned['frontend'])
if front:
 actual=front.children(recursive=True);expected=owned['frontend_windows_console_children']
 assert {p.pid for p in actual}<={p['pid'] for p in expected},'Unexpected child must be reviewed, never broad-killed'
 for child in expected:
  p=exact(child)
  if p:assert p.ppid()==front.pid and Path(p.cmdline()[0]).name.lower()=='conhost.exe'
 front.terminate();front.wait(timeout=15)
for child in owned['frontend_windows_console_children']:
 p=exact(child)
 if p:
  try:p.wait(timeout=5)
  except psutil.TimeoutExpired:
   assert Path(p.cmdline()[0]).name.lower()=='conhost.exe'
   p.terminate();p.wait(timeout=5)
path=Path(r['stop_file'])
if not path.exists():
 with path.open('x',encoding='utf8') as f:json.dump({'nonce':r['stop_nonce'],'requested_at':time.time(),'source':'exact-owned-stop-helper'},f)
else:assert read(path).get('nonce')==r['stop_nonce']
if backend:backend.wait(timeout=30)
for port in owned['ports']:
 with socket.socket() as check:check.bind(('127.0.0.1',port))
for name in ['backend','frontend']:
 assert exact(owned[name]) is None
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
for name,h in r['backend_source_vector'].items():assert sha(REPO.parent/'RSTV4'/name)==h
for name,h in r['protected_external_artifacts'].items():assert sha(Path(name))==h
for name,h in read(OLD/'protected-original-files.json').items():assert sha(Path(r['original'])/name)==h
assert (HERE/'backend-terminal.json').is_file()
result={'status':'EXACT_OWNED_FRONTEND_AND_BACKEND_STOPPED_PORTS_FREE','ports':owned['ports'],'frontend_pid':owned['frontend']['pid'],'backend_pid':owned['backend']['pid'],'known_windows_console_children':owned['frontend_windows_console_children'],'original_files_and_external25_exact':True,'current_backend311_exact':True,'root_preserved':r['root'],'no_other_processes_stopped':True,'scientific_approval':False}
with (HERE/'owned-stop-terminal.json').open('x',encoding='utf8') as f:json.dump(result,f,ensure_ascii=False,indent=2)
print(json.dumps(result,ensure_ascii=False))
