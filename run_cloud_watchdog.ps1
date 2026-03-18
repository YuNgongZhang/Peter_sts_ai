param(
    [Parameter(Mandatory = $true)]
    [string]$StsDir,

    [string]$SteamRoot = "",

    [int]$Instances = 1,

    [string]$PlayerClass = "IRONCLAD",

    [int]$AscensionLevel = 0,

    [string]$Seed = "",

    [string]$DataDir = "training_data",

    [string]$SessionPrefix = "cloud",

    [int]$RestartDelaySeconds = 20,

    [int]$MaxRestarts = 0,

    [switch]$NoAutoStart,

    [switch]$DryRunOnly
)

$ErrorActionPreference = "Stop"

if (-not (Test-Path $StsDir)) {
    throw "STS directory does not exist: $StsDir"
}

$dataRoot = Resolve-Path -LiteralPath "." | ForEach-Object { Join-Path $_ $DataDir }
if (-not (Test-Path $dataRoot)) {
    New-Item -ItemType Directory -Path $dataRoot | Out-Null
}

$watchdogLog = Join-Path $dataRoot "watchdog.log"

function Write-WatchdogLog {
    param([string]$Message)
    $line = "{0} {1}" -f (Get-Date -Format "yyyy-MM-dd HH:mm:ss"), $Message
    Write-Host $line
    Add-Content -Path $watchdogLog -Value $line
}

$restartCount = 0

while ($true) {
    if ($MaxRestarts -gt 0 -and $restartCount -ge $MaxRestarts) {
        Write-WatchdogLog "[stop] reached MaxRestarts=$MaxRestarts"
        break
    }

    $sessionId = "{0}_{1}" -f $SessionPrefix, (Get-Date -Format "yyyyMMdd_HHmmss")
    $launchArgs = @(
        "launch_training.py",
        "--launch-mode", "modthespire",
        "--sts-dir", $StsDir,
        "--instances", $Instances,
        "--player-class", $PlayerClass,
        "--ascension-level", $AscensionLevel,
        "--data-dir", $DataDir,
        "--session-id", $sessionId
    )

    if ($SteamRoot) {
        $launchArgs += @("--steam-root", $SteamRoot)
    }

    if ($Seed) {
        $launchArgs += @("--seed", $Seed)
    }

    if ($NoAutoStart) {
        $launchArgs += "--no-auto-start"
    }

    Write-WatchdogLog "[start] session=$sessionId instances=$Instances"
    & py -3 @launchArgs --dry-run

    if ($DryRunOnly) {
        Write-WatchdogLog "[done] dry-run only"
        break
    }

    & py -3 @launchArgs
    $exitCode = $LASTEXITCODE
    Write-WatchdogLog "[exit] session=$sessionId code=$exitCode"

    $restartCount += 1
    Write-WatchdogLog "[sleep] restarting in $RestartDelaySeconds second(s)"
    Start-Sleep -Seconds $RestartDelaySeconds
}
