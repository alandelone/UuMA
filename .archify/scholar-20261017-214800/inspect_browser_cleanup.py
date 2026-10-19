import subprocess
script=r'''[Console]::OutputEncoding = [System.Text.UTF8Encoding]::new(); Get-CimInstance Win32_Process -Filter "Name = 'chrome.exe'" | Where-Object { $_.CommandLine -like '*archify-visual-check-profile-WyXU9d*' -or $_.CommandLine -like '*archify-visual-check-profile-my0AKa*' } | Select-Object ProcessId,ParentProcessId,ExecutablePath,CreationDate,CommandLine | ConvertTo-Json -Depth 3'''
r=subprocess.run(['powershell','-NoProfile','-Command',script],capture_output=True,text=True,encoding='utf-8',errors='replace')
print(r.stdout or 'No retained-profile Chrome process remains.')
if r.stderr: print(r.stderr)
raise SystemExit(r.returncode)
