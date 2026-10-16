# Start UuMA All-in-One Observatory (Phase 1)
$ErrorActionPreference = "Stop"

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$repoRoot = Split-Path -Parent $scriptDir
Set-Location $repoRoot

$python = Join-Path $repoRoot ".venv\Scripts\python.exe"
if (-not (Test-Path $python)) {
    Write-Error "Virtual environment not found at $python. Please run ./init.sh first."
    exit 1
}

$port = 8790
$hostAddress = "127.0.0.1"

# Generate or read secure token from .uuma-local/observatory.token
$localDir = Join-Path $repoRoot ".uuma-local"
if (-not (Test-Path $localDir)) {
    New-Item -ItemType Directory -Path $localDir -Force | Out-Null
}
$tokenFile = Join-Path $localDir "observatory.token"

$tokenBytes = New-Object byte[] 32
(New-Object Security.Cryptography.RNGCryptoServiceProvider).GetBytes($tokenBytes)
$token = [Convert]::ToBase64String($tokenBytes).Replace("+", "-").Replace("/", "_").TrimEnd("=")
Set-Content -Path $tokenFile -Value $token -NoNewline

$targetUrl = "http://$($hostAddress):$($port)/"

Write-Host "==========================================================" -ForegroundColor Cyan
Write-Host "🔭 正在启动 UuMA All-in-One Observatory (端口 $port)..." -ForegroundColor Green
Write-Host "🌐 本地回环免密直连: $targetUrl" -ForegroundColor Yellow
Write-Host "🔑 远程/非回环访问令牌: $token" -ForegroundColor Gray
Write-Host "==========================================================" -ForegroundColor Cyan

# Launch browser after a short delay
Start-Process powershell -ArgumentList "-NoProfile", "-Command", "Start-Sleep -Seconds 2; Start-Process '$targetUrl'"

# Start FastAPI server via uvicorn
& $python -m uuma.observatory --host $hostAddress --port $port --token $token
