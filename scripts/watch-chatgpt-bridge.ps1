param(
    [string]$TaskName = "UuMA ChatGPT Bridge",
    [int]$Port = 8787
)

# Compatibility no-op for an old task until on-demand migration unregisters it.
# Never restart a service the operator has stopped.
Write-Verbose 'Watchdog retired. Use manage-chatgpt-bridge.ps1 for explicit lifecycle control.'
