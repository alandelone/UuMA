from pathlib import Path
import subprocess
root=Path.cwd()
command="""
$refreshListeners=@(Get-NetTCPConnection -State Listen -LocalPort 8879 -ErrorAction SilentlyContinue | Select-Object LocalAddress,LocalPort,OwningProcess)
$refreshRoot=@(Get-CimInstance Win32_Process -Filter 'ProcessId=91564' | Select-Object ProcessId,ParentProcessId,CommandLine,CreationDate)
[pscustomobject]@{Listeners=$refreshListeners;OriginalRoot=$refreshRoot} | ConvertTo-Json -Depth 4
"""
result=subprocess.run(['powershell','-NoProfile','-Command',command],capture_output=True,text=True,encoding='utf-8')
(root/'.tmp/scholar-intent-correspondence-runtime-inspect-v1.log').write_text(result.stdout+result.stderr,encoding='utf-8')
print(result.stdout+result.stderr)
assert result.returncode==0
