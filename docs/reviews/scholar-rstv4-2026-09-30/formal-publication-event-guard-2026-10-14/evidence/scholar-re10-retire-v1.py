from pathlib import Path
import hashlib
import json
import os
import socket
import sys
import time

import psutil

repo = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(repo / '.tmp/scholar-g11-parallel-v1'))
from runtime_copy_and_serve import snapshot, exclusive_json

here = repo / '.tmp/scholar-re10-retire-v1'
here.mkdir(exist_ok=False)
read = lambda p: json.loads(p.read_text(encoding='utf-8'))
snap = lambda p: json.loads(json.dumps(snapshot(p), ensure_ascii=False))
sha = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()
native = repo / '.tmp/scholar-re10-native-v1'
api = repo / '.tmp/scholar-re10-api-v1'
sources = []
for directory, expected in [(native, 'before-all-tables.json'), (api, 'final-all-tables.json')]:
    receipt = read(directory / 'copy-receipt.json')
    root = Path(receipt['root']).resolve()
    assert root.parent == Path(os.environ['LOCALAPPDATA'], 'Temp').resolve()
    assert root.name.startswith('scui-re10-')
    assert snap(root / 'data/catalog.db') == read(directory / expected)
    original = Path(receipt['source']).resolve()
    assert snap(original / 'data/catalog.db') == read(directory / 'before-all-tables.json')
    assert {p.relative_to(original).as_posix(): sha(p) for p in original.rglob('*')
            if p.is_file() and not p.name.endswith(('-wal', '-shm'))} == read(directory / 'protected-source-files.json')
    sources.append({'directory': str(directory), 'root': str(root), 'original_source_exact': True,
                    'owned_tables_exact': True, 'native_mutations': 0 if directory == native else None})

targets = []
for directory, script in [(native, 'scholar-re10-native-v1.py'), (api, 'scholar-re10-api-v1.py')]:
    ready = read(directory / 'backend-ready.json')
    pid = ready['pid']
    if not psutil.pid_exists(pid):
        targets.append({'pid': pid, 'absent_before': True, 'port': ready['port']})
        continue
    proc = psutil.Process(pid)
    assert str(repo / '.tmp' / script).casefold() in ' '.join(proc.cmdline()).casefold()
    assert proc.cmdline()[-1] == 'serve'
    targets.append({'pid': pid, 'created': proc.create_time(), 'cmdline': proc.cmdline(),
                    'cwd': proc.cwd(), 'port': ready['port'], 'kind': 'owned_backend'})

front = read(native / 'frontend-launched.json')
frontroot = os.path.normcase(os.path.realpath(front['root']))
frontpids = set()
if psutil.pid_exists(front['pid']):
    launcher = psutil.Process(front['pid'])
    assert os.path.normcase(os.path.realpath(launcher.cwd())) == frontroot
    assert '49415' in ' '.join(launcher.cmdline())
    frontpids.update(p.pid for p in launcher.children(recursive=True))
    frontpids.add(launcher.pid)
for connection in psutil.net_connections(kind='tcp'):
    if connection.status == psutil.CONN_LISTEN and connection.laddr.port == front['port']:
        assert connection.pid is not None
        proc = psutil.Process(connection.pid)
        assert os.path.normcase(os.path.realpath(proc.cwd())) == frontroot
        assert proc.name().casefold() in {'node.exe', 'cmd.exe'}
        frontpids.add(proc.pid)
for pid in frontpids:
    proc = psutil.Process(pid)
    assert os.path.normcase(os.path.realpath(proc.cwd())) == frontroot
    assert proc.name().casefold() in {'node.exe', 'cmd.exe'}
    targets.append({'pid': pid, 'created': proc.create_time(), 'cmdline': proc.cmdline(),
                    'cwd': proc.cwd(), 'kind': 'owned_frontend'})
exclusive_json(here / 'verified-targets.json', {'targets': targets, 'sources': sources})

for target in reversed(targets):
    if target.get('absent_before') or not psutil.pid_exists(target['pid']):
        continue
    proc = psutil.Process(target['pid'])
    assert proc.create_time() == target['created']
    assert proc.cmdline() == target['cmdline']
    proc.terminate()
    proc.wait(timeout=15)
ports = [read(native / 'backend-ready.json')['port'], read(api / 'backend-ready.json')['port'], front['port']]
for port in ports:
    with socket.socket() as sock:
        assert sock.connect_ex(('127.0.0.1', port)) != 0
for entry in sources:
    directory = Path(entry['directory'])
    expected = 'before-all-tables.json' if directory == native else 'final-all-tables.json'
    assert snap(Path(entry['root']) / 'data/catalog.db') == read(directory / expected)
exclusive_json(here / 'receipt.json', {'status': 'PASS_ONLY_RE10_OWNED_SERVICES_RETIRED',
                                      'ports_free': ports, 'processes': len(targets),
                                      'original_and_owned_tables_preserved': True,
                                      'original_studio_and_user_kept_bib_page_untouched': True})
print('PASS_ONLY_RE10_OWNED_SERVICES_RETIRED')
