param(
    [Parameter(Mandatory = $true)]
    [string]$StsDir,

    [string]$SteamRoot = "",

    [int]$Instances = 1,

    [string]$PlayerClass = "IRONCLAD",

    [int]$AscensionLevel = 0,

    [string]$Seed = "",

    [string]$DataDir = "training_data",

    [switch]$NoAutoStart,

    [switch]$DryRunOnly
)

$ErrorActionPreference = "Stop"

if (-not (Test-Path $StsDir)) {
    throw "STS directory does not exist: $StsDir"
}

$commonArgs = @(
    "launch_training.py",
    "--launch-mode", "modthespire",
    "--sts-dir", $StsDir,
    "--instances", $Instances,
    "--player-class", $PlayerClass,
    "--ascension-level", $AscensionLevel,
    "--data-dir", $DataDir
)

if ($SteamRoot) {
    $commonArgs += @("--steam-root", $SteamRoot)
}

if ($Seed) {
    $commonArgs += @("--seed", $Seed)
}

if ($NoAutoStart) {
    $commonArgs += "--no-auto-start"
}

Write-Host "[step] validating launch configuration"
& py -3 @commonArgs --dry-run

if ($DryRunOnly) {
    return
}

Write-Host "[step] starting training run"
& py -3 @commonArgs
