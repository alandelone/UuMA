[CmdletBinding()]
param(
    [string]$RuntimeRoot = "",
    [string]$KagVersion = "v0.8.0",
    [string]$OpenSpgHost = "http://127.0.0.1:8887",
    [string]$HermesProfileRoot = (Join-Path $env:LOCALAPPDATA "hermes\profiles\wisdom-oldman"),
    [string]$KagLlmModel = "",
    [string]$KagBaseUrl = "",
    [switch]$SkipModelDownload,
    [switch]$SkipStart
)

$ErrorActionPreference = "Stop"
$repositoryRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
if (-not $RuntimeRoot) {
    $RuntimeRoot = Join-Path $repositoryRoot ".uuma-local\kag"
}
$resolvedRuntime = [IO.Path]::GetFullPath($RuntimeRoot)
$runtimeParent = Split-Path -Parent $resolvedRuntime
New-Item -ItemType Directory -Path $runtimeParent -Force | Out-Null
New-Item -ItemType Directory -Path $resolvedRuntime -Force | Out-Null

function Get-DotEnvValue {
    param([string]$Path, [string]$Key)
    if (-not (Test-Path -LiteralPath $Path)) { return "" }
    foreach ($line in Get-Content -LiteralPath $Path) {
        if ($line -match "^$([regex]::Escape($Key))=(.*)$") { return $Matches[1].Trim() }
    }
    return ""
}

$hermesEnv = Join-Path $HermesProfileRoot ".env"
$hermesConfig = Join-Path $HermesProfileRoot "config.yaml"
$defaultHermesConfig = Join-Path (Join-Path $env:LOCALAPPDATA "hermes") "config.yaml"
$baseUrlWasExplicit = $PSBoundParameters.ContainsKey("KagBaseUrl")
$modelWasExplicit = $PSBoundParameters.ContainsKey("KagLlmModel")
if (-not $env:OPENAI_API_KEY) {
    $openRouterKey = if ($env:OPENROUTER_API_KEY) {
        $env:OPENROUTER_API_KEY
    }
    else {
        Get-DotEnvValue -Path $hermesEnv -Key "OPENROUTER_API_KEY"
    }
    if ($openRouterKey) { $env:OPENAI_API_KEY = $openRouterKey }
}
if (-not $KagBaseUrl -and (Test-Path -LiteralPath $hermesConfig)) {
    $baseLine = Get-Content -LiteralPath $hermesConfig | Where-Object {
        $_ -match '^\s{2}base_url:\s*(.+)$'
    } | Select-Object -First 1
    if ($baseLine -match '^\s{2}base_url:\s*(.+)$') { $KagBaseUrl = $Matches[1].Trim() }
}
if (-not $KagLlmModel -and (Test-Path -LiteralPath $hermesConfig)) {
    $modelLine = Get-Content -LiteralPath $hermesConfig | Where-Object {
        $_ -match '^\s{2}default:\s*(.+)$'
    } | Select-Object -First 1
    if ($modelLine -match '^\s{2}default:\s*(.+)$') { $KagLlmModel = $Matches[1].Trim() }
}
# A Hermes profile may point at an optional localhost inference router that is
# not currently running. When bootstrap auto-discovers such a dead endpoint,
# use the default Hermes provider instead. Explicit CLI choices are preserved.
if (-not $baseUrlWasExplicit -and $KagBaseUrl) {
    $parsedBaseUrl = [Uri]$KagBaseUrl
    $isLocalEndpoint = $parsedBaseUrl.Host -in @("127.0.0.1", "localhost", "::1")
    if ($isLocalEndpoint) {
        $endpointPort = if ($parsedBaseUrl.IsDefaultPort) {
            if ($parsedBaseUrl.Scheme -eq "https") { 443 } else { 80 }
        }
        else { $parsedBaseUrl.Port }
        $listener = Get-NetTCPConnection -State Listen -LocalPort $endpointPort `
            -ErrorAction SilentlyContinue
        if (-not $listener -and (Test-Path -LiteralPath $defaultHermesConfig)) {
            $baseLine = Get-Content -LiteralPath $defaultHermesConfig | Where-Object {
                $_ -match '^\s{2}base_url:\s*(.+)$'
            } | Select-Object -First 1
            if ($baseLine -match '^\s{2}base_url:\s*(.+)$') {
                $KagBaseUrl = $Matches[1].Trim()
            }
            if (-not $modelWasExplicit) {
                $modelLine = Get-Content -LiteralPath $defaultHermesConfig | Where-Object {
                    $_ -match '^\s{2}default:\s*(.+)$'
                } | Select-Object -First 1
                if ($modelLine -match '^\s{2}default:\s*(.+)$') {
                    $KagLlmModel = $Matches[1].Trim()
                }
            }
        }
    }
}
if ($KagBaseUrl) { $env:OPENAI_BASE_URL = $KagBaseUrl }
if ($KagLlmModel) { $env:UUMA_KAG_LLM_MODEL = $KagLlmModel }

foreach ($required in @("OPENAI_API_KEY", "OPENAI_BASE_URL", "UUMA_KAG_LLM_MODEL")) {
    if (-not [Environment]::GetEnvironmentVariable($required)) {
        throw "$required must be set for KAG extraction and reasoning."
    }
}

$composeFile = Join-Path $resolvedRuntime "docker-compose-west.yml"
$composeUrl = "https://raw.githubusercontent.com/OpenSPG/openspg/refs/heads/master/dev/release/docker-compose-west.yml"
if (-not (Test-Path -LiteralPath $composeFile)) {
    Invoke-WebRequest -Uri $composeUrl -OutFile $composeFile
}
$dockerLogRoot = (Join-Path $resolvedRuntime "dozerdb\logs")
New-Item -ItemType Directory -Path $dockerLogRoot -Force | Out-Null
$dockerLogMount = $dockerLogRoot.Replace('\', '/')
$composeContent = Get-Content -LiteralPath $composeFile -Raw
$composeContent = $composeContent.Replace(
    '- $HOME/dozerdb/logs:/logs',
    "- `"${dockerLogMount}:/logs`""
)
Set-Content -LiteralPath $composeFile -Value $composeContent -Encoding utf8

$kagSource = Join-Path $resolvedRuntime "KAG"
if (-not (Test-Path -LiteralPath (Join-Path $kagSource ".git"))) {
    & git clone --depth 1 --branch $KagVersion https://github.com/OpenSPG/KAG.git $kagSource
    if ($LASTEXITCODE -ne 0) { throw "Could not clone OpenSPG/KAG $KagVersion." }
}

$virtualEnv = Join-Path $resolvedRuntime ".venv"
$kagPython = Join-Path $virtualEnv "Scripts\python.exe"
if (-not (Test-Path -LiteralPath $kagPython)) {
    & py -3.11 -m venv $virtualEnv
    if ($LASTEXITCODE -ne 0) { throw "Could not create the KAG Python environment." }
}
& $kagPython -m pip install --upgrade pip
& $kagPython -m pip install -e $kagSource huggingface-hub
if ($LASTEXITCODE -ne 0) { throw "Could not install KAG into the bridge environment." }
# KAG's local bge_m3 implementation imports these packages at runtime but v0.8.0
# does not declare them in requirements.txt. Pin versions from the KAG v0.8 era and
# use PyTorch's official CUDA 12.8 wheel so the local RTX GPU is actually used.
& $kagPython -m pip install "torch==2.8.0+cu128" --index-url https://download.pytorch.org/whl/cu128
if ($LASTEXITCODE -ne 0) { throw "Could not install the CUDA-enabled PyTorch runtime." }
& $kagPython -m pip install `
    "FlagEmbedding==1.3.5" `
    "scikit-learn==1.7.1" `
    "transformers==4.52.4" `
    "datasets==2.19.0" `
    "accelerate==1.7.0" `
    "sentence-transformers==4.1.0" `
    "peft==0.15.2" `
    "huggingface-hub==0.32.4" `
    "onnxruntime==1.23.2" `
    "protobuf==3.20.1" `
    "requests==2.31.0" `
    "tqdm==4.66.1"
if ($LASTEXITCODE -ne 0) { throw "Could not install the local BGE-M3 runtime dependencies." }
# KAG v0.8 pins mcp 1.6 while UuMA's main MCP runtime pins 1.26. The bridge imports only
# UuMA's HTTP adapter module through PYTHONPATH, so do not install UuMA metadata into
# this environment. That keeps both MCP versions isolated and makes pip check useful.
& $kagPython -c "import importlib.util,sys; sys.exit(0 if importlib.util.find_spec('uuma') else 1)"
if ($LASTEXITCODE -eq 0) {
    & $kagPython -m pip uninstall -y uuma *> $null
    if ($LASTEXITCODE -ne 0) { throw "Could not remove UuMA metadata from the KAG environment." }
}
& $kagPython -m pip install "fastapi>=0.104,<1"
if ($LASTEXITCODE -ne 0) { throw "Could not install the KAG bridge HTTP runtime." }
$sourcePath = Join-Path $repositoryRoot "src"
$env:PYTHONPATH = if ($env:PYTHONPATH) {
    "$sourcePath$([IO.Path]::PathSeparator)$env:PYTHONPATH"
}
else {
    $sourcePath
}

$modelPath = Join-Path $resolvedRuntime "models\bge-m3"
if (-not $SkipModelDownload -and -not (Test-Path -LiteralPath (Join-Path $modelPath "config.json"))) {
    New-Item -ItemType Directory -Path $modelPath -Force | Out-Null
    & $kagPython -c (
        "from huggingface_hub import snapshot_download; import sys; " +
        "snapshot_download('BAAI/bge-m3', local_dir=sys.argv[1])"
    ) $modelPath
    if ($LASTEXITCODE -ne 0) { throw "Could not download the local BGE-M3 model." }
}

$configFile = Join-Path $resolvedRuntime "kag_config.yaml"
# Runtime config is generated from the versioned template on every bootstrap;
# environment variables and the recovered project ID supply machine-local values.
Copy-Item -LiteralPath (Join-Path $PSScriptRoot "kag_config.yaml.example") `
    -Destination $configFile -Force
$schemaRoot = Join-Path $resolvedRuntime "schema"
New-Item -ItemType Directory -Path $schemaRoot -Force | Out-Null
Copy-Item -Path (Join-Path $PSScriptRoot "schema\*") -Destination $schemaRoot -Force

$modelConfigPath = $modelPath.Replace('\', '/')
$env:UUMA_BGE_M3_PATH = $modelConfigPath
$env:UUMA_KAG_PROJECT_ID = "1"
$env:UUMA_KAG_CONFIG = $configFile
$env:UUMA_KAG_PYTHON = $kagPython
$env:UUMA_KAG_COMPOSE_FILE = $composeFile
$env:UUMA_KAG_BRIDGE_URL = "http://127.0.0.1:8891"

# OpenSPG validates the project vectorizer inside its server container. Its stock
# image does not include FlagEmbedding, so the uploaded, secret-free metadata copy
# uses KAG's 1024-dimensional mock only for that validation. The bridge's host
# config remains the operative config and always uses the real local BGE-M3 model.
$modelContainerPath = "/uuma/models/bge-m3"
$projectRestoreRoot = Join-Path $resolvedRuntime "project-restore"
New-Item -ItemType Directory -Path $projectRestoreRoot -Force | Out-Null
$projectConfigFile = Join-Path $projectRestoreRoot "kag_config.yaml"
$containerBaseUrl = $env:OPENAI_BASE_URL.Replace("127.0.0.1", "host.docker.internal").Replace("localhost", "host.docker.internal")
$projectConfigContent = Get-Content -LiteralPath (Join-Path $PSScriptRoot "kag_config.yaml.example") -Raw
$projectConfigContent = $projectConfigContent.Replace("{{ OPENAI_BASE_URL }}", $containerBaseUrl)
$projectConfigContent = $projectConfigContent.Replace("{{ OPENAI_API_KEY }}", "uuma-project-validation")
$projectConfigContent = $projectConfigContent.Replace("{{ UUMA_KAG_LLM_MODEL }}", $env:UUMA_KAG_LLM_MODEL)
$projectConfigContent = $projectConfigContent.Replace("{{ UUMA_BGE_M3_PATH }}", $modelContainerPath)
$projectConfigContent = $projectConfigContent.Replace("{{ UUMA_KAG_PROJECT_ID }}", "1")
$projectConfigContent = [regex]::Replace(
    $projectConfigContent,
    '(?m)^  type: maas\r?\n  base_url: ".*"\r?\n  api_key: ".*"\r?\n  model: ".*"\r?\n  enable_check: false$',
    "  type: mock"
)
$projectConfigContent = [regex]::Replace(
    $projectConfigContent,
    '(?m)^  type: bge_m3\r?\n  path: "/uuma/models/bge-m3"\r?\n  vector_dimensions: 1024$',
    "  type: mock`n  vector_dimensions: 1024",
    1
)
Set-Content -LiteralPath $projectConfigFile -Value $projectConfigContent -Encoding utf8

if (-not $SkipStart) {
    # Docker Desktop can emit a benign seccomp warning on stderr even when the
    # command succeeds. Run this readiness probe through cmd so PowerShell's
    # ErrorActionPreference does not convert that warning into a terminating
    # error; the native exit code remains the source of truth.
    & cmd.exe /d /c "docker info >NUL 2>NUL"
    if ($LASTEXITCODE -ne 0) {
        $dockerDesktop = Join-Path $env:ProgramFiles "Docker\Docker\Docker Desktop.exe"
        if (-not (Test-Path -LiteralPath $dockerDesktop)) {
            throw "Docker Desktop is not installed at its standard path."
        }
        Start-Process -FilePath $dockerDesktop -WindowStyle Hidden
        $dockerDeadline = [DateTime]::UtcNow.AddMinutes(2)
        do {
            Start-Sleep -Seconds 3
            & cmd.exe /d /c "docker info >NUL 2>NUL"
            $dockerReady = $LASTEXITCODE -eq 0
        } until ($dockerReady -or [DateTime]::UtcNow -ge $dockerDeadline)
        if (-not $dockerReady) { throw "Docker Desktop did not become ready within two minutes." }
    }
    & docker compose -p uuma-wisdom-kag -f $composeFile up -d
    if ($LASTEXITCODE -ne 0) { throw "The OpenSPG Docker runtime could not be started." }
    $deadline = [DateTime]::UtcNow.AddMinutes(3)
    do {
        try {
            $healthResponse = Invoke-WebRequest -Uri "$OpenSpgHost/public/v1/project" -TimeoutSec 5
            $ready = $healthResponse.StatusCode -eq 200
        }
        catch {
            $ready = $false
        }
        if (-not $ready) { Start-Sleep -Seconds 3 }
    } until ($ready -or [DateTime]::UtcNow -ge $deadline)
    if (-not $ready) { throw "OpenSPG did not become HTTP-ready within three minutes." }

    Push-Location $projectRestoreRoot
    try {
        & (Join-Path $virtualEnv "Scripts\knext.exe") project restore --host_addr $OpenSpgHost --proj_path $resolvedRuntime
        if ($LASTEXITCODE -ne 0) { throw "Could not create or restore the Uuma OpenSPG project." }
        $projectId = (& $kagPython -c "import sys, yaml; print(yaml.safe_load(open(sys.argv[1], encoding='utf-8'))['project']['id'])" $projectConfigFile).Trim()
        if (-not $projectId -or $projectId -notmatch '^\d+$') { throw "OpenSPG returned an invalid project id." }
        $env:UUMA_KAG_PROJECT_ID = $projectId
        $hostConfigContent = Get-Content -LiteralPath $configFile -Raw
        $hostConfigContent = [regex]::Replace($hostConfigContent, '(?m)^  id:.*$', "  id: `"$projectId`"", 1)
        Set-Content -LiteralPath $configFile -Value $hostConfigContent -Encoding utf8

        Push-Location $resolvedRuntime
        try {
        & (Join-Path $virtualEnv "Scripts\knext.exe") schema commit
        if ($LASTEXITCODE -ne 0) { throw "Could not commit the Uuma universal KAG schema." }
        }
        finally {
            Pop-Location
        }
    }
    finally {
        Pop-Location
    }

    # Replace only the bridge instance owned by this runtime. Listening child
    # processes can use the base interpreter behind the venv launcher, so stop
    # both the port owner and an exact venv launcher before starting one copy.
    $bridgePids = @(
        Get-NetTCPConnection -State Listen -LocalPort 8891 -ErrorAction SilentlyContinue |
            Select-Object -ExpandProperty OwningProcess -Unique
    )
    $bridgePids += @(
        Get-CimInstance Win32_Process | Where-Object {
            $_.ExecutablePath -eq $kagPython -and $_.CommandLine -match 'uuma\.kag_bridge'
        } | Select-Object -ExpandProperty ProcessId
    )
    foreach ($bridgePid in ($bridgePids | Sort-Object -Unique)) {
        Stop-Process -Id $bridgePid -Force -ErrorAction SilentlyContinue
    }
    Start-Process -FilePath $kagPython -ArgumentList @("-m", "uuma.kag_bridge") `
        -WorkingDirectory $resolvedRuntime -WindowStyle Hidden
}

@{
    base_url = $env:OPENAI_BASE_URL
    model = $env:UUMA_KAG_LLM_MODEL
    bge_m3_path = $modelConfigPath
    project_id = $env:UUMA_KAG_PROJECT_ID
} | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $resolvedRuntime "runtime.json") -Encoding utf8

Write-Host "KAG runtime prepared at $resolvedRuntime"
Write-Host "Re-run scripts\deploy-hermes.ps1, then restart Hermes so Knowledge MCP receives KAG settings."
