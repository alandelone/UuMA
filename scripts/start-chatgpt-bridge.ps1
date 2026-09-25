param(
    [Parameter(Mandatory = $true)][string]$PythonExe,
    [Parameter(Mandatory = $true)][string]$ProjectRoot,
    [Parameter(Mandatory = $true)][string]$DataDir,
    [int]$Port = 8787
)

$ErrorActionPreference = "Stop"
$logPath = Join-Path $DataDir "chatgpt-bridge\lifecycle.log"
New-Item -ItemType Directory -Path (Split-Path -Parent $logPath) -Force | Out-Null
try {
    Add-Content -LiteralPath $logPath -Value "$(Get-Date -Format o) launcher-start"
    Set-Location -LiteralPath $ProjectRoot
    $env:PYTHONPATH = Join-Path $ProjectRoot "src"
    & $PythonExe -m uuma.chatgpt_cli --data-dir $DataDir --port $Port serve
    $exitCode = $LASTEXITCODE
    Add-Content -LiteralPath $logPath -Value "$(Get-Date -Format o) launcher-exit code=$exitCode"
    exit $exitCode
}
catch {
    Add-Content -LiteralPath $logPath -Value "$(Get-Date -Format o) launcher-error $($_.Exception.Message)"
    throw
}
