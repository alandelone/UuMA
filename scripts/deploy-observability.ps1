param(
    [string]$HermesExe = "$env:LOCALAPPDATA\hermes\hermes-agent\venv\Scripts\hermes.exe",
    [string]$ProjectRoot = (Split-Path -Parent $PSScriptRoot),
    [string[]]$Profiles = @("default", "brainstormer", "scholar", "wisdom-oldman", "forge-lab-bot"),
    [string]$PhoenixEndpoint = "http://127.0.0.1:6006/v1/traces",
    [string]$PhoenixProject = "hermes",
    [bool]$CaptureTelemetryContent = $false
)

$ErrorActionPreference = "Stop"
$hermesHome = Join-Path $env:LOCALAPPDATA "hermes"
$profilesRoot = Join-Path $hermesHome "profiles"
$pluginSource = Join-Path $ProjectRoot "integrations\hermes\uuma_observability"
$hermesPython = Join-Path (Split-Path -Parent $HermesExe) "python.exe"

function Set-DotEnvValue {
    param([string]$Path, [string]$Key, [string]$Value)
    $lines = if (Test-Path -LiteralPath $Path) { Get-Content -LiteralPath $Path } else { @() }
    $replacement = "$Key=$Value"
    $matched = $false
    $updated = foreach ($line in $lines) {
        if ($line -match "^$([regex]::Escape($Key))=") {
            $matched = $true
            $replacement
        }
        else {
            $line
        }
    }
    if (-not $matched) {
        $updated = @($updated) + $replacement
    }
    Set-Content -LiteralPath $Path -Value $updated -Encoding utf8
}

if (-not (Test-Path -LiteralPath $hermesPython)) {
    throw "Hermes Python runtime not found at '$hermesPython'."
}
if (-not (Test-Path -LiteralPath (Join-Path $pluginSource "plugin.yaml"))) {
    throw "UuMA observability plugin source not found at '$pluginSource'."
}

$uvCommand = Get-Command uv -ErrorAction SilentlyContinue
if ($uvCommand) {
    & $uvCommand.Source pip install --python $hermesPython "arize-phoenix-otel>=0.17,<1"
}
else {
    & $hermesPython -m pip install "arize-phoenix-otel>=0.17,<1"
}
if ($LASTEXITCODE -ne 0) {
    throw "Failed to install the Phoenix OpenTelemetry dependency in Hermes."
}

foreach ($profile in $Profiles) {
    $profileHome = if ($profile -eq "default") {
        $hermesHome
    }
    else {
        Join-Path $profilesRoot $profile
    }
    if (-not (Test-Path -LiteralPath $profileHome)) {
        Write-Warning "Skipping missing Hermes profile '$profile'."
        continue
    }
    $target = Join-Path $profileHome "plugins\uuma_observability"
    New-Item -ItemType Directory -Path $target -Force | Out-Null
    Copy-Item -Path (Join-Path $pluginSource "*") -Destination $target -Recurse -Force

    $envFile = Join-Path $profileHome ".env"
    Set-DotEnvValue -Path $envFile -Key "UUMA_PHOENIX_ENABLED" -Value "true"
    Set-DotEnvValue -Path $envFile -Key "UUMA_PHOENIX_ENDPOINT" -Value $PhoenixEndpoint
    Set-DotEnvValue -Path $envFile -Key "UUMA_PHOENIX_PROJECT" -Value $PhoenixProject
    Set-DotEnvValue -Path $envFile -Key "UUMA_OBSERVABILITY_CAPTURE_CONTENT" -Value (
        $CaptureTelemetryContent.ToString().ToLowerInvariant()
    )
    $previousHermesHome = $env:HERMES_HOME
    try {
        $env:HERMES_HOME = $profileHome
        & $HermesExe plugins enable uuma_observability --no-allow-tool-override
        if ($LASTEXITCODE -ne 0) {
            throw "Failed to enable observability for Hermes profile '$profile'."
        }
    }
    finally {
        $env:HERMES_HOME = $previousHermesHome
    }
    Write-Host "Configured Phoenix tracing for Hermes profile '$profile'."
}

Write-Host "Restart the Hermes gateway to load the observability plugin."
