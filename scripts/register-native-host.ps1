<#
.SYNOPSIS
    Registers the UuMA Lab Bot Chrome Native Messaging Host in the Windows CurrentUser registry.
.DESCRIPTION
    Generates the host manifest with the resolved repository paths and registers it under
    HKCU:\Software\Google\Chrome\NativeMessagingHosts\com.uuma.labbot.
#>
[CmdletBinding()]
param(
    [string]$ExtensionId = "knldjmfmopnflpmmkcfjedmhhajpkgcl",
    [switch]$Force
)

$ErrorActionPreference = "Stop"

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Definition
$repoRoot = (Resolve-Path (Join-Path $scriptDir "..")).Path
$launcherPath = (Resolve-Path (Join-Path $scriptDir "run-native-host.bat")).Path
$manifestDir = Join-Path $repoRoot "extension\labbot-browser"

if (-not (Test-Path $manifestDir)) {
    New-Item -ItemType Directory -Path $manifestDir -Force | Out-Null
}

$manifestPath = Join-Path $manifestDir "com.uuma.labbot.json"
$manifest = @{
    name = "com.uuma.labbot"
    description = "UuMA Lab Bot Chrome Native Messaging Host"
    path = $launcherPath
    type = "stdio"
    allowed_origins = @(
        "chrome-extension://$ExtensionId/"
    )
}

$manifest | ConvertTo-Json -Depth 5 | Set-Content -Path $manifestPath -Encoding UTF8
Write-Host "Generated native host manifest at: $manifestPath"

$regPath = "HKCU:\Software\Google\Chrome\NativeMessagingHosts\com.uuma.labbot"
if (-not (Test-Path "HKCU:\Software\Google\Chrome\NativeMessagingHosts")) {
    New-Item -Path "HKCU:\Software\Google\Chrome\NativeMessagingHosts" -Force | Out-Null
}

New-Item -Path $regPath -Value $manifestPath -Force | Out-Null
Write-Host "Successfully registered native host at $regPath -> $manifestPath"

