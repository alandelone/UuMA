import ctypes
import json
import subprocess

expression = "Get-CimInstance Win32_Process | Where-Object {$_.Name -eq 'python.exe' -and $_.CommandLine -like '*scholar-experiment-controls-restore-preview-v2.py*' -and $_.CommandLine -notlike '*uuma.session*'} | Select-Object ProcessId,ParentProcessId,CreationDate,CommandLine | ConvertTo-Json"

def query(command):
    r = subprocess.run(['powershell.exe', '-NoProfile', '-Command', command],
                       capture_output=True, text=True, check=True)
    return json.loads(r.stdout) if r.stdout.strip() else None

found = query(expression)
processes = found if isinstance(found, list) else [found] if found else []
assert 1 <= len(processes) <= 2
ids = {int(p['ProcessId']) for p in processes}
leaves = [p for p in processes if not any(int(q['ParentProcessId']) == int(p['ProcessId']) for q in processes)]
assert len(leaves) == 1
process = leaves[0]
pid = int(process['ProcessId'])
fresh = query(f"Get-CimInstance Win32_Process -Filter 'ProcessId={pid}' | Select-Object ProcessId,ParentProcessId,CreationDate,CommandLine | ConvertTo-Json")
assert fresh == process
kernel = ctypes.WinDLL('kernel32', use_last_error=True)
kernel.OpenProcess.restype = ctypes.c_void_p
kernel.TerminateProcess.argtypes = [ctypes.c_void_p, ctypes.c_uint]
kernel.CloseHandle.argtypes = [ctypes.c_void_p]
handle = kernel.OpenProcess(1, False, pid)
assert handle
try:
    assert kernel.TerminateProcess(handle, 1)
finally:
    kernel.CloseHandle(handle)
print('Stopped only the verified bootstrap observer', pid)
