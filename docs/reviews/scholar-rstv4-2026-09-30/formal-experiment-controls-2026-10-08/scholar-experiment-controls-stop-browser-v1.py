import json
import ctypes
import subprocess
from pathlib import Path

repo = Path(__file__).resolve().parents[1]
meta = json.loads((repo / '.tmp/scholar-experiment-controls-browser-v1.json').read_text())
def query(expression):
    r = subprocess.run(['powershell.exe', '-NoProfile', '-Command', expression],
                       capture_output=True, text=True, check=True)
    return json.loads(r.stdout) if r.stdout.strip() else None

listener = query(f'Get-NetTCPConnection -LocalPort {int(meta["port"])} -State Listen -ErrorAction SilentlyContinue | Select-Object OwningProcess | ConvertTo-Json')
if listener:
    assert isinstance(listener, dict)
    pid = int(listener['OwningProcess'])
    expression = f"Get-CimInstance Win32_Process -Filter 'ProcessId = {pid}' | Select-Object ProcessId,CommandLine,CreationDate | ConvertTo-Json"
    process = query(expression)
    assert 'scholar-experiment-controls-browser-server-v1.py' in process['CommandLine']
    assert 'uuma.session' not in process['CommandLine']
    assert query(expression) == process
    kernel = ctypes.WinDLL('kernel32', use_last_error=True)
    kernel.OpenProcess.restype = ctypes.c_void_p
    kernel.TerminateProcess.argtypes = [ctypes.c_void_p, ctypes.c_uint]
    kernel.CloseHandle.argtypes = [ctypes.c_void_p]
    handle = kernel.OpenProcess(1, False, pid)
    assert handle, ctypes.get_last_error()
    try:
        assert kernel.TerminateProcess(handle, 0), ctypes.get_last_error()
    finally:
        kernel.CloseHandle(handle)
    print('Stopped owned browser fixture', pid)
