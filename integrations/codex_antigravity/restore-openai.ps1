param(
    [switch]$Preview,
    [switch]$Quiet
)

# Deliberately independent of Codex, Python, the gateway and the remote server.
$ErrorActionPreference = 'Stop'
$repoRoot = Split-Path (Split-Path $PSScriptRoot -Parent) -Parent
$stateDir = Join-Path $repoRoot '.uuma-local\codex-antigravity-ui-20261102'
$configPath = Join-Path $env:USERPROFILE '.codex\config.toml'
$utf8 = New-Object System.Text.UTF8Encoding($false)
$beginMarker = '# BEGIN UUMA ANTIGRAVITY PILOT'
$endMarker = '# END UUMA ANTIGRAVITY PILOT'

try {
    $original = [System.IO.File]::ReadAllText($configPath, $utf8)
    $pattern = '(?s)' + [regex]::Escape($beginMarker) + '\r?\n.*?' +
        [regex]::Escape($endMarker) + '\r?\n?'
    $blocks = [regex]::Matches($original, $pattern)
    if ($original.Contains($beginMarker) -and $blocks.Count -ne 2) {
        throw 'Pilot configuration blocks changed. No file was overwritten.'
    }
    $restored = [regex]::Replace($original, $pattern, '')
    $previousPath = Join-Path $stateDir 'previous-routing.json'
    if ($blocks.Count -gt 0 -and (Test-Path -LiteralPath $previousPath)) {
        $previous = Get-Content -LiteralPath $previousPath -Raw -Encoding UTF8 |
            ConvertFrom-Json
        $prefix = ''
        foreach ($key in @('model_provider', 'model_catalog_json')) {
            $value = $previous.$key
            if ($null -ne $value) {
                $encoded = ConvertTo-Json -InputObject ([string]$value) -Compress
                $prefix += $key + ' = ' + $encoded + "`n"
            }
        }
        $restored = $prefix + $restored
    }
    if ($Preview) {
        Write-Output ('Restore preview: {0} pilot blocks; Python and gateway not required.' -f
            $blocks.Count)
        exit 0
    }
    if ([System.IO.File]::ReadAllText($configPath, $utf8) -cne $original) {
        throw 'Configuration changed during recovery. Retry; no file was overwritten.'
    }
    if ($blocks.Count -gt 0) {
        [System.IO.Directory]::CreateDirectory($stateDir) | Out-Null
        $backup = Join-Path $stateDir ('config.before-independent-restore-' +
            [guid]::NewGuid().ToString('N') + '.toml')
        [System.IO.File]::Copy($configPath, $backup, $false)
        [System.IO.File]::WriteAllText($configPath, $restored, $utf8)
    }
    $startup = Join-Path $env:APPDATA (
        'Microsoft\Windows\Start Menu\Programs\Startup\UuMA Antigravity Gateway.lnk')
    if (Test-Path -LiteralPath $startup) { Remove-Item -LiteralPath $startup }
    $message = 'OpenAI routing restored. Fully quit and reopen the desktop app, then ' +
        'choose a GPT model or open a new chat. Chats and credentials were not deleted.'
    Write-Output $message
    if (-not $Quiet) {
        Add-Type -AssemblyName System.Windows.Forms
        [System.Windows.Forms.MessageBox]::Show($message, 'UuMA recovery') | Out-Null
    }
} catch {
    $message = 'Recovery did not finish: ' + $_.Exception.Message
    if (-not $Quiet) {
        Add-Type -AssemblyName System.Windows.Forms
        [System.Windows.Forms.MessageBox]::Show($message, 'UuMA recovery') | Out-Null
    }
    Write-Error $message
    exit 1
}
