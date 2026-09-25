param(
    [Parameter(Mandatory = $true)][string]$PythonExe,
    [Parameter(Mandatory = $true)][string]$ProjectRoot,
    [Parameter(Mandatory = $true)][string]$DataDir,
    [Parameter(Mandatory = $true)][string]$ProfileHome
)

$ErrorActionPreference = "Stop"
$resolvedPython = (Resolve-Path -LiteralPath $PythonExe).Path
$resolvedProject = (Resolve-Path -LiteralPath $ProjectRoot).Path
$resolvedProfile = (Resolve-Path -LiteralPath $ProfileHome).Path
$env:UUMA_DATA_DIR = $DataDir
$lifecycleLog = Join-Path $DataDir "orbit-runner-lifecycle.log"
$sourcePath = Join-Path $resolvedProject "src"
$env:PYTHONPATH = if ($env:PYTHONPATH) {
    "$sourcePath$([IO.Path]::PathSeparator)$env:PYTHONPATH"
}
else {
    $sourcePath
}

function Write-RunnerLifecycle {
    param([string]$Message)

    $timestamp = (Get-Date).ToUniversalTime().ToString("o")
    Add-Content -LiteralPath $lifecycleLog -Value "$timestamp $Message" -Encoding utf8
}

$exitCode = 1
Write-RunnerLifecycle "launcher_started pid=$PID profile=$resolvedProfile"
try {
    & $resolvedPython -m uuma.orbit_runner --profile-home $resolvedProfile
    $exitCode = $LASTEXITCODE
}
catch {
    Write-RunnerLifecycle "launcher_error pid=$PID message=$($_.Exception.Message)"
    throw
}
finally {
    Write-RunnerLifecycle "launcher_exited pid=$PID exit_code=$exitCode"
}
exit $exitCode
