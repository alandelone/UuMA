param([string]$Target = '192.168.55.2', [switch]$IncludeGraph)
$ErrorActionPreference = 'Stop'
$ports = @(8765, 8768, 8769)
if ($IncludeGraph) { $ports += 8766 }
foreach ($port in $ports) {
    if (Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue) {
        throw "Port $port is already in use. No process was stopped."
    }
}
$arguments = @('-N', '-T', '-o', 'BatchMode=yes', '-o', 'StrictHostKeyChecking=yes',
    '-o', 'ExitOnForwardFailure=yes', '-o', 'ServerAliveInterval=15',
    '-o', 'ServerAliveCountMax=3')
foreach ($port in $ports) {
    $arguments += @('-L', "127.0.0.1:${port}:127.0.0.1:${port}")
}
$arguments += @('-R', '127.0.0.1:8770:127.0.0.1:8770', $Target)
& ssh @arguments
if ($LASTEXITCODE -ne 0) { throw "SSH tunnel exited with $LASTEXITCODE" }
