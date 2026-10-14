import json
import subprocess

command = "[pscustomobject]@{Process=(Get-CimInstance Win32_Process -Filter 'ProcessId=63780' | Select-Object ProcessId,ParentProcessId,ExecutablePath,CommandLine,CreationDate); Listener=(Get-NetTCPConnection -State Listen -LocalPort 8877 | Select-Object LocalPort,OwningProcess)} | ConvertTo-Json -Depth 5"
result = json.loads(subprocess.run(['powershell', '-NoProfile', '-Command', command], capture_output=True, text=True, check=True).stdout)
listener = result['Listener']['OwningProcess']
child = json.loads(subprocess.run(['powershell', '-NoProfile', '-Command', f"Get-CimInstance Win32_Process -Filter 'ProcessId={listener}' | Select-Object ProcessId,ParentProcessId,ExecutablePath,CommandLine,CreationDate | ConvertTo-Json"], capture_output=True, text=True, check=True).stdout)
print(json.dumps({'root': result, 'child': child}))
