param(
    [string]$HermesExe = "$env:LOCALAPPDATA\hermes\hermes-agent\venv\Scripts\hermes.exe",
    [string]$PythonExe = (Get-Command python).Source,
    [string]$ProjectRoot = (Split-Path -Parent $PSScriptRoot),
    [string]$DataDir = "$env:LOCALAPPDATA\UuMA",
    [string[]]$GeminiAllowedRoots = @((Split-Path -Parent $ProjectRoot), $DataDir),
    [string]$ESchematicRoot = (Join-Path (Split-Path -Parent $ProjectRoot) "eSchematic_skillset"),
    [string]$ESchematicPython = "",
    [string]$RSTV4Root = (Join-Path (Split-Path -Parent $ProjectRoot) "RSTV4"),
    [string]$KagBridgeUrl = "http://127.0.0.1:8891",
    [string]$KagRuntimeRoot = (Join-Path $ProjectRoot ".uuma-local\kag"),
    [bool]$KagAutoRecover = $true,
    [int]$KagIdleSeconds = 1800,
    [bool]$QuestionOrbitEnabled = $false,
    [bool]$EnablePhoenixTelemetry = $true,
    [string]$PhoenixEndpoint = "http://127.0.0.1:6006/v1/traces",
    [string]$PhoenixProject = "hermes",
    [bool]$CaptureTelemetryContent = $false,
    [bool]$PruneSpecialistSkills = $true,
    [string]$SkillQuarantineRoot = ""
)

$ErrorActionPreference = "Stop"
$HermesExe = (Resolve-Path -LiteralPath $HermesExe).Path
$PythonExe = (Resolve-Path -LiteralPath $PythonExe).Path
$sourcePath = Join-Path $ProjectRoot "src"
$profilesRoot = Join-Path $env:LOCALAPPDATA "hermes\profiles"
$defaultHome = Join-Path $env:LOCALAPPDATA "hermes"
$pluginSource = Join-Path $ProjectRoot "integrations\hermes\uuma_audit"
$controlGuardPluginSource = Join-Path $ProjectRoot "integrations\hermes\uuma_control_guard"
$observabilityPluginSource = Join-Path $ProjectRoot "integrations\hermes\uuma_observability"
$hermesPython = Join-Path (Split-Path -Parent $HermesExe) "python.exe"
$forgeSkillsSource = Join-Path $ProjectRoot "profiles\forge-lab-bot\skills"
$brainstormerSkillsSource = Join-Path $ProjectRoot "profiles\brainstormer\skills"
$wisdomSkillsSource = Join-Path $ProjectRoot "profiles\wisdom-oldman\skills"
$rstv4Python = Join-Path $RSTV4Root ".venv\Scripts\python.exe"
$rstv4SkillSource = Join-Path $RSTV4Root "skills\rstv4-research"
$resolvedSkillQuarantineRoot = if ($SkillQuarantineRoot) {
    $SkillQuarantineRoot
}
else {
    Join-Path $DataDir ("skill-quarantine\" + (Get-Date -Format "yyyyMMdd-HHmmssfff"))
}

if (-not $ESchematicPython) {
    $ESchematicPython = (& py -3.12 -c "import sys; print(sys.executable)").Trim()
}
if (-not (Test-Path -LiteralPath (Join-Path $ESchematicRoot "skills\eschematic\SKILL.md"))) {
    throw "eSchematic skill package not found at '$ESchematicRoot'."
}

$profiles = @(
    @{ Id = "brainstormer"; Description = "Structured ideation, challenge, decisions, and build-ready design artifacts." },
    @{ Id = "scholar"; Description = "Evidence-driven full-cycle scientific research with user-owned scientific decisions." },
    @{ Id = "wisdom-oldman"; Description = "Governed KAG discovery, formation, gap analysis, maintenance, and evidence-linked answers." },
    @{ Id = "forge-lab-bot"; Description = "Hardware lab inventory, build traceability, procurement advice, and engineering lessons." }
)

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

function Remove-DotEnvKeys {
    param([string]$Path, [string[]]$Keys)
    if (-not (Test-Path -LiteralPath $Path)) { return }
    $keySet = @{}
    foreach ($key in $Keys) { $keySet[$key] = $true }
    $updated = foreach ($line in Get-Content -LiteralPath $Path) {
        $candidate = if ($line -match '^([^#=]+)=') { $Matches[1].Trim() } else { "" }
        if (-not $keySet.ContainsKey($candidate)) { $line }
    }
    Set-Content -LiteralPath $Path -Value $updated -Encoding utf8
}

function Install-AuditPlugin {
    param([string]$Profile, [string]$ProfileHome)
    $target = Join-Path $ProfileHome "plugins\uuma_audit"
    New-Item -ItemType Directory -Path $target -Force | Out-Null
    Copy-Item -LiteralPath (Join-Path $pluginSource "plugin.yaml") -Destination $target -Force
    Copy-Item -LiteralPath (Join-Path $pluginSource "__init__.py") -Destination $target -Force
}

function Install-ControlGuardPlugin {
    param([string]$ProfileHome)
    $target = Join-Path $ProfileHome "plugins\uuma_control_guard"
    New-Item -ItemType Directory -Path $target -Force | Out-Null
    Copy-Item -Path (Join-Path $controlGuardPluginSource "*") -Destination $target -Recurse -Force
}

function Install-ObservabilityPlugin {
    param([string]$ProfileHome)
    $target = Join-Path $ProfileHome "plugins\uuma_observability"
    New-Item -ItemType Directory -Path $target -Force | Out-Null
    Copy-Item -Path (Join-Path $observabilityPluginSource "*") -Destination $target -Recurse -Force
    $previousHermesHome = $env:HERMES_HOME
    try {
        $env:HERMES_HOME = $ProfileHome
        & $HermesExe plugins enable uuma_observability --no-allow-tool-override
        if ($LASTEXITCODE -ne 0) { throw "Failed to enable the UuMA observability plugin." }
    }
    finally {
        $env:HERMES_HOME = $previousHermesHome
    }
}

function Install-ForgeLabSkills {
    param([string]$ProfileHome)
    $category = Join-Path $ProfileHome "skills\hardware-lab"
    New-Item -ItemType Directory -Path $category -Force | Out-Null
    foreach ($skillName in @(
        "eschematic",
        "eschematic-bridge",
        "lab-inventory",
        "lab-receiving",
        "lab-procurement-advice",
        "lab-build-traceability",
        "lab-as-built",
        "lab-commissioning",
        "lab-worklog",
        "lab-failure-analysis",
        "lab-engineering-lessons"
    )) {
        $source = Join-Path $forgeSkillsSource $skillName
        $target = Join-Path $category $skillName
        New-Item -ItemType Directory -Path $target -Force | Out-Null
        Copy-Item -Path (Join-Path $source "*") -Destination $target -Recurse -Force
    }
}

function Install-BrainstormerSkills {
    param([string]$ProfileHome)
    foreach ($skillName in @(
        "discussion-state",
        "discussion-reentry",
        "discussion-checkpoint",
        "artifact-readiness"
    )) {
        $source = Join-Path $brainstormerSkillsSource $skillName
        $target = Join-Path (Join-Path $ProfileHome "skills") $skillName
        New-Item -ItemType Directory -Path $target -Force | Out-Null
        Copy-Item -Path (Join-Path $source "*") -Destination $target -Recurse -Force
    }
}

function Sync-ProfileSoul {
    param([string]$ProfileHome, [string]$AgentId)
    $sourcePath = Join-Path $ProjectRoot "profiles\$AgentId\SOUL.md"
    $targetPath = Join-Path $ProfileHome "SOUL.md"
    $sourceText = (Get-Content -LiteralPath $sourcePath -Raw).Trim()
    $current = if (Test-Path -LiteralPath $targetPath) {
        Get-Content -LiteralPath $targetPath -Raw
    }
    else { "" }
    $begin = "<!-- UUMA-MANAGED-SOUL-START -->"
    $end = "<!-- UUMA-MANAGED-SOUL-END -->"
    $managed = "$begin`r`n$sourceText`r`n$end"
    if ($current.Contains($begin) -and $current.Contains($end)) {
        $pattern = "(?s)$([regex]::Escape($begin)).*?$([regex]::Escape($end))"
        $updated = [regex]::Replace($current, $pattern, $managed)
    }
    elseif (-not $current.Trim() -or $sourceText.StartsWith($current.Trim())) {
        $updated = $managed
    }
    else {
        $pending = "$targetPath.uuma-pending"
        Set-Content -LiteralPath $pending -Value $managed -Encoding utf8
        Write-Warning "SOUL customization conflict for '$AgentId'; review '$pending'."
        return
    }
    if ($current.Trim() -ne $updated.Trim()) {
        if (Test-Path -LiteralPath $targetPath) {
            Copy-Item -LiteralPath $targetPath -Destination "$targetPath.uuma-backup" -Force
        }
        Set-Content -LiteralPath $targetPath -Value $updated -Encoding utf8
    }
}

function Install-ScholarResearchSkill {
    param([string]$ProfileHome)
    if (-not (Test-Path -LiteralPath $rstv4SkillSource)) {
        throw "RSTV4 Scholar skill package not found at '$rstv4SkillSource'."
    }
    $target = Join-Path $ProfileHome "skills\rstv4-research"
    New-Item -ItemType Directory -Path $target -Force | Out-Null
    Copy-Item -Path (Join-Path $rstv4SkillSource "*") -Destination $target -Recurse -Force
}

function Install-WisdomSkills {
    param([string]$ProfileHome)
    if (-not (Test-Path -LiteralPath $wisdomSkillsSource)) {
        throw "Wisdom-Oldman skill packages not found at '$wisdomSkillsSource'."
    }
    foreach ($skillName in @(
        "wisdom-investigate",
        "wisdom-evidence-research",
        "wisdom-knowledge-formation",
        "wisdom-answer",
        "wisdom-maintain-kag",
        "wisdom-question-orbit"
    )) {
        $source = Join-Path $wisdomSkillsSource $skillName
        $target = Join-Path (Join-Path $ProfileHome "skills") $skillName
        New-Item -ItemType Directory -Path $target -Force | Out-Null
        Copy-Item -Path (Join-Path $source "*") -Destination $target -Recurse -Force
    }
}

function Prune-SpecialistProfileSkills {
    param([string]$ProfileHome, [string]$AgentId)
    if (-not $PruneSpecialistSkills) { return }
    if (@("brainstormer", "wisdom-oldman", "forge-lab-bot") -notcontains $AgentId) { return }
    & $PythonExe -m uuma.specialist_skills `
        --profile-home $ProfileHome `
        --agent-id $AgentId `
        --quarantine-root $resolvedSkillQuarantineRoot `
        --apply
    if ($LASTEXITCODE -ne 0) {
        throw "Failed to prune inherited skills for Hermes profile '$AgentId'."
    }
}

function Repair-ScholarMemory {
    param([string]$ProfileHome)
    $memoryPath = Join-Path $ProfileHome "memories\MEMORY.md"
    if (-not (Test-Path -LiteralPath $memoryPath)) { return }
    $current = Get-Content -LiteralPath $memoryPath -Raw
    if ($current -notmatch "MediaCrawler|XHS|Antigravity") { return }
    Copy-Item -LiteralPath $memoryPath -Destination "$memoryPath.uuma-backup" -Force
    @'
User communicates primarily in Chinese and values concise, evidence-first research work.

RSTV4 is the research source of truth. Always separate local evidence from current-world evidence,
preserve provenance, and propose rather than silently changing scientific decisions. The user owns
research scope, RQs, methods, claims, interpretations, and conclusions.
'@ | Set-Content -LiteralPath $memoryPath -Encoding utf8
}

function Set-HermesProfileConfig {
    param([string]$ProfileHome, [string]$Role, [string]$AgentId, [bool]$EnableRSTV4 = $false)
    $arguments = @(
        (Join-Path $ProjectRoot "scripts\configure-hermes-profile.py"),
        "--config", (Join-Path $ProfileHome "config.yaml"),
        "--role", $Role,
        "--agent-id", $AgentId,
        "--python-exe", $PythonExe,
        "--source-path", $sourcePath,
        "--data-dir", $DataDir,
        "--gemini-allowed-roots", ($GeminiAllowedRoots -join [IO.Path]::PathSeparator),
        "--eschematic-root", $ESchematicRoot,
        "--eschematic-python", $ESchematicPython,
        "--kag-bridge-url", $KagBridgeUrl,
        "--kag-auto-recover", $KagAutoRecover.ToString().ToLowerInvariant(),
        "--kag-idle-seconds", $KagIdleSeconds,
        "--question-orbit-enabled", $QuestionOrbitEnabled.ToString().ToLowerInvariant()
    )
    $kagComposeFile = Join-Path $KagRuntimeRoot "docker-compose-west.yml"
    $kagPython = Join-Path $KagRuntimeRoot ".venv\Scripts\python.exe"
    $kagConfig = Join-Path $KagRuntimeRoot "kag_config.yaml"
    $kagRuntimeConfig = Join-Path $KagRuntimeRoot "runtime.json"
    if (Test-Path -LiteralPath $kagComposeFile) {
        $arguments += @("--kag-compose-file", $kagComposeFile)
    }
    if (Test-Path -LiteralPath $kagPython) {
        $arguments += @("--kag-python", $kagPython)
    }
    if (Test-Path -LiteralPath $kagConfig) {
        $arguments += @("--kag-config", $kagConfig)
    }
    if ($AgentId -eq "wisdom-oldman") {
        $arguments += @("--kag-secrets-file", (Join-Path $ProfileHome ".env"))
    }
    if (Test-Path -LiteralPath $kagRuntimeConfig) {
        $runtimeSettings = Get-Content -LiteralPath $kagRuntimeConfig -Raw | ConvertFrom-Json
        $arguments += @(
            "--kag-base-url", $runtimeSettings.base_url,
            "--kag-model", $runtimeSettings.model,
            "--kag-project-id", $runtimeSettings.project_id,
            "--bge-m3-path", $runtimeSettings.bge_m3_path
        )
    }
    if ($EnableRSTV4) {
        $arguments += @("--rstv4-root", $RSTV4Root, "--rstv4-python", $rstv4Python)
    }
    & $PythonExe @arguments
    if ($LASTEXITCODE -ne 0) { throw "Failed to configure Hermes profile '$AgentId'." }
}

$env:PYTHONPATH = $sourcePath
$env:UUMA_DATA_DIR = $DataDir
if ($EnablePhoenixTelemetry) {
    if (-not (Test-Path -LiteralPath $hermesPython)) {
        throw "Hermes Python runtime not found at '$hermesPython'."
    }
    $uvCommand = Get-Command uv -ErrorAction SilentlyContinue
    if ($uvCommand) {
        & $uvCommand.Source pip install --python $hermesPython "arize-phoenix-otel>=0.17,<1"
    }
    else {
        & $hermesPython -m pip install "arize-phoenix-otel>=0.17,<1"
    }
    if ($LASTEXITCODE -ne 0) { throw "Failed to install Hermes Phoenix telemetry dependency." }
}
if (-not (Test-Path -LiteralPath $rstv4Python)) {
    & (Join-Path $RSTV4Root "scripts\bootstrap-rstv4.ps1") -PythonExe $PythonExe -ProjectRoot $RSTV4Root
    if ($LASTEXITCODE -ne 0) { throw "RSTV4 bootstrap failed." }
}
& $PythonExe -m uuma init
if ($LASTEXITCODE -ne 0) { throw "UuMA initialization failed." }

function Sync-OrchestratorSoul {
    $source = Get-Content -LiteralPath (
        Join-Path $ProjectRoot "profiles\orchestrator\SOUL.addendum.md"
    ) -Raw
    $targetPath = Join-Path $defaultHome "SOUL.md"
    $current = Get-Content -LiteralPath $targetPath -Raw
    $begin = "<!-- UUMA-ORCHESTRATOR-POLICY-V1 -->"
    $end = "<!-- UUMA-ORCHESTRATOR-POLICY-END -->"
    if ($current.Contains($begin) -and $current.Contains($end)) {
        $pattern = "(?s)$([regex]::Escape($begin)).*?$([regex]::Escape($end))"
        $updated = [regex]::Replace($current, $pattern, $source.Trim())
    }
    elseif ($current.Contains($begin)) {
        # Older deployments appended the managed block at EOF without an end marker.
        $updated = $current.Substring(0, $current.IndexOf($begin)) + $source.Trim() + "`r`n"
    }
    else {
        $updated = $current.TrimEnd() + "`r`n`r`n" + $source.Trim() + "`r`n"
    }
    if ($current -ne $updated) {
        Copy-Item -LiteralPath $targetPath -Destination "$targetPath.uuma-backup" -Force
        Set-Content -LiteralPath $targetPath -Value $updated -Encoding utf8
    }
}

Sync-OrchestratorSoul
Install-ControlGuardPlugin -ProfileHome $defaultHome

Set-HermesProfileConfig -ProfileHome $defaultHome -Role "control" -AgentId "orchestrator"
Set-DotEnvValue -Path (Join-Path $defaultHome ".env") -Key "UUMA_DATA_DIR" -Value $DataDir
Set-DotEnvValue -Path (Join-Path $defaultHome ".env") -Key "UUMA_INGEST_URL" -Value "http://127.0.0.1:8766/ingest/hermes"
Set-DotEnvValue -Path (Join-Path $defaultHome ".env") -Key "UUMA_TOKEN_FILE" -Value (Join-Path $DataDir "tokens.json")
Set-DotEnvValue -Path (Join-Path $defaultHome ".env") -Key "UUMA_PHOENIX_ENABLED" -Value $EnablePhoenixTelemetry.ToString().ToLowerInvariant()
Set-DotEnvValue -Path (Join-Path $defaultHome ".env") -Key "UUMA_PHOENIX_ENDPOINT" -Value $PhoenixEndpoint
Set-DotEnvValue -Path (Join-Path $defaultHome ".env") -Key "UUMA_PHOENIX_PROJECT" -Value $PhoenixProject
Set-DotEnvValue -Path (Join-Path $defaultHome ".env") -Key "UUMA_OBSERVABILITY_CAPTURE_CONTENT" -Value $CaptureTelemetryContent.ToString().ToLowerInvariant()
Set-DotEnvValue -Path (Join-Path $defaultHome ".env") -Key "RSTV4_ROOT" -Value $RSTV4Root
Set-DotEnvValue -Path (Join-Path $defaultHome ".env") -Key "RSTV4_PYTHON" -Value $rstv4Python
Install-AuditPlugin -Profile "default" -ProfileHome $defaultHome
Install-ObservabilityPlugin -ProfileHome $defaultHome

foreach ($profile in $profiles) {
    $id = $profile.Id
    $profileHome = Join-Path $profilesRoot $id
    & $HermesExe profile show $id *> $null
    $created = $LASTEXITCODE -ne 0
    if ($created) {
        & $HermesExe profile create --clone-from default --description $profile.Description $id
        if ($LASTEXITCODE -ne 0) { throw "Failed to create Hermes profile '$id'." }
    }

    Sync-ProfileSoul -ProfileHome $profileHome -AgentId $id

    $isScholar = $id -eq "scholar"
    Set-HermesProfileConfig -ProfileHome $profileHome -Role "worker" -AgentId $id -EnableRSTV4 $isScholar
    Set-DotEnvValue -Path (Join-Path $profileHome ".env") -Key "UUMA_DATA_DIR" -Value $DataDir
    Set-DotEnvValue -Path (Join-Path $profileHome ".env") -Key "UUMA_INGEST_URL" -Value "http://127.0.0.1:8766/ingest/hermes"
    Set-DotEnvValue -Path (Join-Path $profileHome ".env") -Key "UUMA_TOKEN_FILE" -Value (Join-Path $DataDir "tokens.json")
    if ($isScholar) {
        Set-DotEnvValue -Path (Join-Path $profileHome ".env") -Key "RSTV4_ROOT" -Value $RSTV4Root
        Set-DotEnvValue -Path (Join-Path $profileHome ".env") -Key "RSTV4_PYTHON" -Value $rstv4Python
    }
    if ($id -eq "brainstormer") {
        Install-BrainstormerSkills -ProfileHome $profileHome
    }
    Set-DotEnvValue -Path (Join-Path $profileHome ".env") -Key "UUMA_PHOENIX_ENABLED" -Value $EnablePhoenixTelemetry.ToString().ToLowerInvariant()
    Set-DotEnvValue -Path (Join-Path $profileHome ".env") -Key "UUMA_PHOENIX_ENDPOINT" -Value $PhoenixEndpoint
    Set-DotEnvValue -Path (Join-Path $profileHome ".env") -Key "UUMA_PHOENIX_PROJECT" -Value $PhoenixProject
    Set-DotEnvValue -Path (Join-Path $profileHome ".env") -Key "UUMA_OBSERVABILITY_CAPTURE_CONTENT" -Value $CaptureTelemetryContent.ToString().ToLowerInvariant()
    Remove-DotEnvKeys -Path (Join-Path $profileHome ".env") -Keys @(
        "GITHUB_TOKEN",
        "NOTION_API_KEY"
    )
    Install-AuditPlugin -Profile $id -ProfileHome $profileHome
    Install-ControlGuardPlugin -ProfileHome $profileHome
    Install-ObservabilityPlugin -ProfileHome $profileHome
    if ($isScholar) {
        Install-ScholarResearchSkill -ProfileHome $profileHome
        Repair-ScholarMemory -ProfileHome $profileHome
    }
    if ($id -eq "wisdom-oldman") {
        Install-WisdomSkills -ProfileHome $profileHome
    }
    if ($id -eq "forge-lab-bot") {
        Install-ForgeLabSkills -ProfileHome $profileHome
    }
    Prune-SpecialistProfileSkills -ProfileHome $profileHome -AgentId $id
}

Write-Host "UuMA Hermes profiles, MCP boundaries, audit/observability plugins, and Kanban board are configured."
Write-Host "Restart the Hermes gateway after this script so it reloads profile and plugin configuration."
