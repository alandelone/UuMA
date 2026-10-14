import json
import subprocess
from pathlib import Path

repo = Path(__file__).resolve().parents[1]
command = r"""
$all = Get-CimInstance Win32_Process
$ids = [System.Collections.Generic.HashSet[int]]::new()
[void]$ids.Add(75360)
do { $added = $false; foreach ($p in $all) { if ($ids.Contains([int]$p.ParentProcessId) -and $ids.Add([int]$p.ProcessId)) { $added = $true } } } while ($added)
[pscustomobject]@{
 Processes = @($all | Where-Object { $ids.Contains([int]$_.ProcessId) } | Select-Object ProcessId,ParentProcessId,ExecutablePath,CommandLine,CreationDate)
 Listener = @(Get-NetTCPConnection -State Listen -LocalPort 3004 | Select-Object LocalPort,OwningProcess)
 Memory = (Get-CimInstance Win32_OperatingSystem | Select-Object TotalVisibleMemorySize,FreePhysicalMemory,TotalVirtualMemorySize,FreeVirtualMemory)
} | ConvertTo-Json -Depth 7
"""
observed = json.loads(subprocess.run(['powershell','-NoProfile','-Command',command], capture_output=True, text=True, check=True).stdout)
with (repo / '.tmp/scholar-template-frontend-owner-v1.json').open('x', encoding='utf-8') as handle:
    json.dump(observed, handle, indent=2)
for file in ['rules/scholar-native-acceptance.md', 'repomemory/findings.md', 'stage-gates/03-execution-brief.md']:
    path = repo / file
    with path.open('a', encoding='utf-8') as handle:
        handle.write('\n\n2026-10-08 template execution correction: isolated build v2 restored its sibling import, then the Node build exited 0xC0000409 at the RSC phase; immediately observed free virtual memory 855208 KiB. Treat memory pressure as an execution limitation, not proof of a product defect or a successful build. Verify and pause only the exact owned development frontend descendant tree, bound Node heap to 1536 MiB and Rust worker pool to two, rebuild in a fresh isolated container, and preserve all original services and artifacts. Native observations must distinguish closing preview contents from actual author inputs, and await the actual Undo transition and saved compensation. A dialog waitFor(hidden) returned no_matches timeout; one early Undo click had no effect and the independent r18 receipt was preserved, then a fresh visible-page action performed compensation. Never repeat an adoption or infer Undo from the old saved badge. A session progress write raised transient OSError22 before build execution; the next wrapped inspection succeeded. No lifecycle checks bypassed.\n')
print(json.dumps(observed, ensure_ascii=False))
