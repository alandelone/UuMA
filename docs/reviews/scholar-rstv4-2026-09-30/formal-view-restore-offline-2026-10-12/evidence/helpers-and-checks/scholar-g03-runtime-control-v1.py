from pathlib import Path
import hashlib, json, os, socket, sqlite3, subprocess, sys, time
sys.stdout.reconfigure(encoding='utf-8')
repo = Path.cwd(); out = repo / '.tmp/scholar-g03-native-v1'
read = lambda p: json.loads(Path(p).read_text(encoding='utf-8'))
db = Path(read(repo / '.tmp/scholar-citation-source-native-v1.json')['root']) / 'data/catalog.db'
sha = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()
def tables():
    with sqlite3.connect(f'file:{db.as_posix()}?mode=ro', uri=True) as conn:
        conn.row_factory = sqlite3.Row
        conn.execute('PRAGMA query_only=ON')
        return {r[0]: [dict(x) for x in conn.execute(f'SELECT * FROM "{r[0]}" ORDER BY rowid')] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")}
def ps(code):
    result = subprocess.run(['powershell', '-NoProfile', '-Command', code], capture_output=True, encoding='utf-8-sig', check=True)
    assert not result.stderr.strip(), result.stderr
    return json.loads(result.stdout or 'null')
def row(pid):
    return ps(f"Get-CimInstance Win32_Process -Filter 'ProcessId={pid}' | Select-Object ProcessId,ParentProcessId,CommandLine,CreationDate | ConvertTo-Json")
def listening(port):
    values = ps(f"@(Get-NetTCPConnection -State Listen | Where-Object LocalPort -eq {port} | Select-Object -ExpandProperty OwningProcess) | ConvertTo-Json -Compress")
    return [values] if isinstance(values, int) else values or []
def stop(chain):
    for saved in chain: assert row(saved['ProcessId']) == saved
    result = []
    for saved in chain:
        pid = saved['ProcessId']; cmd = saved['CommandLine'].replace("'", "''"); epoch = int(saved['CreationDate'].split('(')[1].split(')')[0])
        state = ps(f"$taskProcess=Get-CimInstance Win32_Process -Filter 'ProcessId={pid}'; if ($null -eq $taskProcess) {{ '{{\"state\":\"ALREADY_EXITED\"}}' }} else {{ if ($taskProcess.CommandLine -cne '{cmd}' -or $taskProcess.ParentProcessId -ne {saved['ParentProcessId']} -or ([DateTimeOffset]$taskProcess.CreationDate).ToUnixTimeMilliseconds() -ne {epoch}) {{ throw 'Owned runtime identity changed' }}; Stop-Process -Id {pid} -Force -ErrorAction Stop; '{{\"state\":\"STOPPED_VERIFIED\"}}' }}")
        result.append({'pid': pid, **state})
    return result
def start(helper, port, label):
    assert not listening(port)
    python = repo / '.uuma-local/scholar-collection-verification-v1/Scripts/python.exe'
    assert python.is_file() and helper.is_file()
    with (out / f'{label}.log').open('x', encoding='utf-8') as log:
        process = subprocess.Popen([str(python), str(helper)], cwd=repo, env=os.environ.copy(), stdout=log, stderr=subprocess.STDOUT, creationflags=subprocess.CREATE_NO_WINDOW)
    deadline = time.monotonic() + 20
    while time.monotonic() < deadline:
        try:
            with socket.create_connection(('127.0.0.1', port), timeout=1): break
        except OSError: time.sleep(.2)
    assert process.poll() is None and listening(port)
    listeners = listening(port); assert len(listeners) == 1
    listener = row(listeners[0]); chain = [listener]
    if listener['ProcessId'] != process.pid:
        assert listener['ParentProcessId'] == process.pid
        chain.append(row(process.pid))
    assert all(helper.name in item['CommandLine'] for item in chain)
    return chain
mode = sys.argv[1]; before = tables(); digest = sha(db)
(out / f'{mode}-before-all-tables.json').write_text(json.dumps(before, ensure_ascii=False, indent=2), encoding='utf-8')
assert len(before['studio_model_calls']) == 14 and len(before['studio_chat_messages']) == 15
assert all(r['status'] not in {'RUNNING', 'QUEUED'} for t in ['studio_jobs', 'research_discussion_jobs'] for r in before[t])
front = read(repo / '.tmp/scholar-g03-runtime-v2-refresh-v1.json')['new_verified_port3008_chain']
assert all(row(p['ProcessId']) == p for p in front)
if mode == 'catalog':
    chain = start(repo / '.tmp/scholar-g03-catalog-server-v1.py', 8875, 'catalog-server')
    receipt = {'mode': mode, 'chain': chain, 'port': 8875}
elif mode == 'adopt-catalog':
    listeners = listening(8875); assert len(listeners) == 1
    listener = row(listeners[0]); parent = row(listener['ParentProcessId']); chain = [listener, parent]
    helper = repo / '.tmp/scholar-g03-catalog-server-v1.py'
    assert all(str(helper) in item['CommandLine'] for item in chain)
    assert (out / 'catalog-server.log').is_file() and (out / 'catalog-server.log').stat().st_size == 0
    receipt = {'mode': mode, 'chain': chain, 'port': 8875, 'context_correction': 'The prior startup succeeded; PowerShell serialized one listener as an integer. Adopt only that exact helper chain without launching another process.'}
elif mode == 'offline':
    chain = read(out.parent / 'scholar-g02-typed-native-v1/runtime.json')['new_verified_port8881_chain']
    assert listening(8881) == [chain[0]['ProcessId']]
    receipt = {'mode': mode, 'stops': stop(chain), 'port': 8881}
    assert not listening(8881)
elif mode == 'online':
    chain = start(repo / '.tmp/scholar-g02-typed-native-server-v1.py', 8881, 'reconnected-server')
    receipt = {'mode': mode, 'chain': chain, 'port': 8881}
elif mode == 'close-catalog':
    chain = read(out / 'catalog-runtime.json')['chain']
    assert listening(8875) == [chain[0]['ProcessId']]
    receipt = {'mode': mode, 'stops': stop(chain), 'port': 8875}
else: raise AssertionError(mode)
after = tables()
assert before == after and sha(db) == digest
assert all(row(p['ProcessId']) == p for p in front)
receipt.update(status='PASS', all109tables_exact=True, database_bytes_exact=True, frontend_unchanged=True, no_new_model_calls=True)
(out / f'{"catalog" if mode == "adopt-catalog" else mode}-runtime.json').write_text(json.dumps(receipt, indent=2), encoding='utf-8')
print(json.dumps(receipt), flush=True)
