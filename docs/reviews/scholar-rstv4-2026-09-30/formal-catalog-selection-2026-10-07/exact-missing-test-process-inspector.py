import subprocess
from pathlib import Path
repo=Path(__file__).resolve().parents[1]
script=r'''
Get-CimInstance Win32_Process | Where-Object { $_.CommandLine -like '*scholar-existing-paper-full-v1.py*' -or $_.CommandLine -like '*pytest*scui-full-xfvb7xt0*' } | Select-Object ProcessId,ParentProcessId,CommandLine | ConvertTo-Json -Depth 4
'''
subprocess.run(['powershell','-NoProfile','-Command',script],cwd=repo,check=True)
