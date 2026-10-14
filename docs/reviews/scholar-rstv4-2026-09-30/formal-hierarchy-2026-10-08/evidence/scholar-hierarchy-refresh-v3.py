from pathlib import Path
repo=Path(__file__).resolve().parents[1]
source=(repo/'.tmp/scholar-hierarchy-refresh-v2.py').read_text(encoding='utf-8')
start=source.index('query="""');end=source.index('"""',start+9)+3
query='''query="""
$OutputEncoding = [Console]::OutputEncoding = [System.Text.UTF8Encoding]::new()
$all = Get-CimInstance Win32_Process
$ids = [System.Collections.Generic.HashSet[int]]::new()
[void]$ids.Add(61984)
[void]$ids.Add(32792)
do { $added=$false; foreach ($p in $all) { if ($ids.Contains([int]$p.ParentProcessId) -and $ids.Add([int]$p.ProcessId)) { $added=$true } } } while ($added)
[pscustomobject]@{Processes=@($all | Where-Object { $ids.Contains([int]$_.ProcessId) } | Select-Object ProcessId,ParentProcessId,CommandLine,CreationDate);Listeners=@(Get-NetTCPConnection -State Listen -LocalPort 3004,8877 | Select-Object LocalAddress,LocalPort,OwningProcess)} | ConvertTo-Json -Depth 5
"""'''
source=source[:start]+query+source[end:]
source=source.replace('capture_output=True,text=True,check=True','capture_output=True,text=True,encoding="utf-8",check=True')
source=source.replace('scholar-hierarchy-refresh-v2.json','scholar-hierarchy-refresh-v3.json')
exec(compile(source,__file__,'exec'))
