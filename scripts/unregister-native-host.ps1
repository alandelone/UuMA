<#
.SYNOPSIS
    Unregisters the UuMA Lab Bot Chrome Native Messaging Host from Windows CurrentUser registry.
#>
[CmdletBinding()]
param()

$ErrorActionPreference = "SilentlyContinue"
$regPath = "HKCU:\Software\Google\Chrome\NativeMessagingHosts\com.uuma.labbot"

if (Test-Path $regPath) {
    Remove-Item -Path $regPath -Force
    Write-Host "Removed native host registry key: $regPath"
} else {
    Write-Host "Registry key does not exist: $regPath"
}
