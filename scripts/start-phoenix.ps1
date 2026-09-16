param(
    [ValidateSet("auto", "docker", "python")]
    [string]$Runtime = "auto",
    [string]$ProjectRoot = (Split-Path -Parent $PSScriptRoot),
    [string]$DataDir = "$env:LOCALAPPDATA\UuMA"
)

$ErrorActionPreference = "Stop"
$healthUrl = "http://127.0.0.1:6006/healthz"

function Test-PhoenixReady {
    try {
        $response = Invoke-WebRequest -Uri $healthUrl -TimeoutSec 2
        return $response.StatusCode -ge 200 -and $response.StatusCode -lt 500
    }
    catch {
        return $false
    }
}

function Wait-PhoenixReady {
    for ($attempt = 0; $attempt -lt 60; $attempt++) {
        if (Test-PhoenixReady) { return $true }
        Start-Sleep -Seconds 1
    }
    return $false
}

if (Test-PhoenixReady) {
    Write-Host "Phoenix is already ready at http://127.0.0.1:6006."
    exit 0
}

$dockerReady = $false
if ($Runtime -in @("auto", "docker") -and (Get-Command docker -ErrorAction SilentlyContinue)) {
    docker info *> $null
    $dockerReady = $LASTEXITCODE -eq 0
}

if ($Runtime -eq "docker" -and -not $dockerReady) {
    throw "Docker was requested but its engine is not running."
}

if ($dockerReady) {
    $composeFile = Join-Path $ProjectRoot "deploy\observability\compose.yaml"
    docker compose -f $composeFile up -d
    if ($LASTEXITCODE -ne 0) {
        throw "Phoenix failed to start in Docker."
    }
}
else {
    $runtimeDir = Join-Path $DataDir "phoenix-runtime"
    $venvDir = Join-Path $runtimeDir "venv"
    $pythonExe = Join-Path $venvDir "Scripts\python.exe"
    $phoenixExe = Join-Path $venvDir "Scripts\phoenix.exe"
    $workingDir = Join-Path $runtimeDir "data"
    $logDir = Join-Path $runtimeDir "logs"
    New-Item -ItemType Directory -Path $workingDir, $logDir -Force | Out-Null

    if (-not (Test-Path -LiteralPath $pythonExe)) {
        & py -3.12 -m venv $venvDir
        if ($LASTEXITCODE -ne 0) { throw "Failed to create the local Phoenix runtime." }
    }
    & $pythonExe -m pip install "arize-phoenix==20.8.0"
    if ($LASTEXITCODE -ne 0) { throw "Failed to install the local Phoenix service." }

    $previousWorkingDir = $env:PHOENIX_WORKING_DIR
    $previousExternalResources = $env:PHOENIX_ALLOW_EXTERNAL_RESOURCES
    $previousHost = $env:PHOENIX_HOST
    $previousPythonUtf8 = $env:PYTHONUTF8
    try {
        $env:PHOENIX_WORKING_DIR = $workingDir
        $env:PHOENIX_ALLOW_EXTERNAL_RESOURCES = "false"
        $env:PHOENIX_HOST = "127.0.0.1"
        $env:PYTHONUTF8 = "1"
        Start-Process -FilePath $phoenixExe -ArgumentList "serve" -WindowStyle Hidden `
            -RedirectStandardOutput (Join-Path $logDir "phoenix.out.log") `
            -RedirectStandardError (Join-Path $logDir "phoenix.err.log")
    }
    finally {
        $env:PHOENIX_WORKING_DIR = $previousWorkingDir
        $env:PHOENIX_ALLOW_EXTERNAL_RESOURCES = $previousExternalResources
        $env:PHOENIX_HOST = $previousHost
        $env:PYTHONUTF8 = $previousPythonUtf8
    }
}

if (-not (Wait-PhoenixReady)) {
    throw "Phoenix started but did not become ready at http://127.0.0.1:6006."
}
Write-Host "Phoenix is ready at http://127.0.0.1:6006."
