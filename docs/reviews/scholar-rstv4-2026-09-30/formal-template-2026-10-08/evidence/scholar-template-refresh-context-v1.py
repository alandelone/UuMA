from pathlib import Path

repo = Path(__file__).resolve().parents[1]
note = '''

## 2026-10-08 Studio template service ownership

Refresh v1 failed before any backup/write/stop: Windows venv launcher63780 owns child76468,
which owns listener8877. Both current exact source command lines and child->root ancestry
independently read. A PID from a launch receipt is not necessarily the listener PID. Verify
both identities and direct ancestry before stopping only that listener; retain original owner
receipts, and record the replacement launch and actual listener. No unrelated process cleanup.
'''
for name in ['repomemory/findings.md', 'rules/scholar-native-acceptance.md']:
    with (repo / name).open('a', encoding='utf-8') as handle:
        handle.write(note)
source = (repo / '.tmp/scholar-template-refresh-v1.py').read_text(encoding='utf-8')
source = source.replace('scholar-template-native-before-v1', 'scholar-template-native-before-v2')
source = source.replace('scholar-template-services-v1', 'scholar-template-services-v2')
source = source.replace('scholar-template-studio-v1', 'scholar-template-studio-v2')
source = source.replace("assert owner['Process']['ProcessId'] == owner['Listener']['OwningProcess'] == 63780",
'''assert owner['Process']['ProcessId'] == 63780
listener = owner['Listener']['OwningProcess']
child = json.loads(subprocess.run(['powershell', '-NoProfile', '-Command',
    f"Get-CimInstance Win32_Process -Filter 'ProcessId={listener}' | Select-Object ProcessId,ParentProcessId,CommandLine | ConvertTo-Json"],
    capture_output=True, text=True, check=True).stdout)
assert child['ProcessId'] == listener and child['ParentProcessId'] == 63780
assert 'scholar-revision-isolated-services-v1.py' in child['CommandLine']
owner['child'] = child''')
source = source.replace("'Stop-Process -Id 63780 -ErrorAction Stop'", "f'Stop-Process -Id {listener} -ErrorAction Stop'")
with (repo / '.tmp/scholar-template-refresh-v2.py').open('x', encoding='utf-8') as handle:
    handle.write(source)
