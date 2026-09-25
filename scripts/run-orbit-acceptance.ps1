param(
    [Parameter(Mandatory = $true)][ValidateSet("seed", "report", "stop")][string]$Mode,
    [Parameter(Mandatory = $true)][string]$PythonExe,
    [Parameter(Mandatory = $true)][string]$ProjectRoot,
    [Parameter(Mandatory = $true)][string]$DataDir,
    [Parameter(Mandatory = $true)][string]$ProfileHome,
    [Parameter(Mandatory = $true)][string]$OutputPath
)

$ErrorActionPreference = "Stop"
$resolvedPython = (Resolve-Path -LiteralPath $PythonExe).Path
$resolvedProject = (Resolve-Path -LiteralPath $ProjectRoot).Path
$resolvedProfile = (Resolve-Path -LiteralPath $ProfileHome).Path
$scriptPath = (Resolve-Path -LiteralPath (
    Join-Path $resolvedProject "scripts\verify-orbit-deployment.py"
)).Path
$env:UUMA_DATA_DIR = $DataDir
$sourcePath = Join-Path $resolvedProject "src"
$env:PYTHONPATH = if ($env:PYTHONPATH) {
    "$sourcePath$([IO.Path]::PathSeparator)$env:PYTHONPATH"
}
else {
    $sourcePath
}

& $resolvedPython $scriptPath $Mode `
    --profile-home $resolvedProfile `
    --output $OutputPath
exit $LASTEXITCODE
