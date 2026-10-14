import json
import subprocess
from pathlib import Path

repo = Path(__file__).resolve().parents[1]
prior = json.loads((repo / '.tmp/scholar-template-frontend-owner-v1.json').read_text(encoding='utf-8'))
assert prior['Listener'] == [{'LocalPort': 3004, 'OwningProcess': 78244}]
command = r"""
$leaf = Get-CimInstance Win32_Process -Filter 'ProcessId=78244'
$parent = Get-CimInstance Win32_Process -Filter 'ProcessId=18988'
$npm = Get-CimInstance Win32_Process -Filter 'ProcessId=41788'
$root = Get-CimInstance Win32_Process -Filter 'ProcessId=75360'
if ($leaf.ParentProcessId -ne 18988 -or $parent.ParentProcessId -ne 41788 -or $npm.ParentProcessId -ne 75360) { throw 'Owned ancestry changed' }
if ($root.CommandLine -ne 'cmd.exe /c npm run dev -- --port 3004') { throw 'Owned root identity changed' }
if ($leaf.CommandLine -notlike '*writing-studio*vinext*cli.js*dev --port 3004*') { throw 'Owned listener identity changed' }
$listeners = @(Get-NetTCPConnection -State Listen -LocalPort 3004)
if ($listeners.Count -ne 1 -or $listeners[0].OwningProcess -ne 78244) { throw 'Port ownership changed' }
[pscustomobject]@{ Leaf = ($leaf | Select-Object ProcessId,ParentProcessId,CommandLine,CreationDate); Root = ($root | Select-Object ProcessId,CommandLine,CreationDate) } | ConvertTo-Json -Depth 5
"""
observed = json.loads(subprocess.run(['powershell','-NoProfile','-Command',command], capture_output=True, text=True, check=True).stdout)
for kind, pid in [('Leaf',78244),('Root',75360)]:
    original = next(p for p in prior['Processes'] if p['ProcessId'] == pid)
    assert observed[kind]['CreationDate'] == original['CreationDate']
subprocess.run(['powershell','-NoProfile','-Command',command + '\nStop-Process -Id 78244 -ErrorAction Stop'], check=True, stdout=subprocess.DEVNULL)
with (repo / '.tmp/scholar-template-paused-dev-v1.json').open('x', encoding='utf-8') as handle:
    json.dump({'verified_before_stop': observed, 'stopped_only_listener': 78244, 'owned_root':75360,
               'original_golden_services_untouched': True, 'database_reset':False}, handle, indent=2)
source = (repo / '.tmp/scholar-template-build-v2.py').read_text(encoding='utf-8')
source = source.replace('scholar-template-build-v2.', 'scholar-template-build-v3.')
source = source.replace("NODE_OPTIONS='--max-old-space-size=4096'", "NODE_OPTIONS='--max-old-space-size=1536', RAYON_NUM_THREADS='2', UV_THREADPOOL_SIZE='2'")
with (repo / '.tmp/scholar-template-build-v3.py').open('x', encoding='utf-8') as handle:
    handle.write(source)
