<#
.SYNOPSIS
  Uninstall the MT5 Research Agent.

.DESCRIPTION
  Removes the virtual environment, launcher, and Start Menu shortcut.

  Safety:
    - Preserves your research data (config.json and the data/ folder with
      results and artifacts) BY DEFAULT.
    - Use -RemoveUserData to also delete config.json and data/ (you will be
      asked to confirm).
    - NEVER deletes MetaTrader 5, EA source, or compiled .ex5 files.

.PARAMETER InstallDir
  The directory the app was installed into.
  Default: %LOCALAPPDATA%\MT5ResearchAgent

.PARAMETER RemoveUserData
  Also remove config.json and the data/ folder (requires confirmation).

.PARAMETER DryRun
  Print the planned actions without changing anything.

.EXAMPLE
  powershell -ExecutionPolicy Bypass -File scripts\uninstall.ps1
#>
[CmdletBinding()]
param(
  [string]$InstallDir = (Join-Path $env:LOCALAPPDATA "MT5ResearchAgent"),
  [switch]$RemoveUserData,
  # Explicit opt-in to the default behaviour (preserve config.json and data/).
  # Provided so `uninstall.ps1 -PreserveUserData` reads clearly; it overrides
  # -RemoveUserData if both are passed.
  [switch]$PreserveUserData,
  [switch]$DryRun
)

if ($PreserveUserData) { $RemoveUserData = $false }

$ErrorActionPreference = "Stop"

function Step($message) { Write-Host "==> $message" -ForegroundColor Cyan }
function Plan($message) { Write-Host "    [dry-run] $message" -ForegroundColor DarkGray }

Step "MT5 Research Agent uninstaller"
Write-Host "    install: $InstallDir"

if (-not (Test-Path $InstallDir)) {
  Write-Host "Nothing to do: $InstallDir does not exist." -ForegroundColor Yellow
  return
}

$venv = Join-Path $InstallDir ".venv"
$launcher = Join-Path $InstallDir "mt5-research-agent.cmd"
$dataDir = Join-Path $InstallDir "data"
$configFile = Join-Path $InstallDir "config.json"
$shortcut = Join-Path $env:APPDATA "Microsoft\Windows\Start Menu\Programs\MT5 Research Agent.lnk"

$alwaysRemove = @($venv, $launcher, $shortcut)
$dataRemove = @($dataDir, $configFile)

if ($DryRun) {
  foreach ($p in $alwaysRemove) { Plan "remove $p" }
  if ($RemoveUserData) { foreach ($p in $dataRemove) { Plan "remove (user data) $p" } }
  else { Write-Host "    user data preserved (config.json, data/). Use -RemoveUserData to delete it." }
  Step "Dry run complete. No changes were made."
  return
}

Step "Removing application files"
foreach ($p in $alwaysRemove) {
  if (Test-Path $p) { Remove-Item -Recurse -Force $p; Write-Host "    removed $p" }
}

if ($RemoveUserData) {
  $answer = Read-Host "Delete research data (config.json and data/ with results/artifacts)? Type YES to confirm"
  if ($answer -ceq "YES") {
    foreach ($p in $dataRemove) {
      if (Test-Path $p) { Remove-Item -Recurse -Force $p; Write-Host "    removed $p" }
    }
  } else {
    Write-Host "    user data kept (confirmation not given)." -ForegroundColor Yellow
  }
} else {
  Write-Host "    user data preserved. Re-run with -RemoveUserData to delete it." -ForegroundColor Green
}

# Remove the install dir only if it is now empty.
if ((Get-ChildItem -Force $InstallDir | Measure-Object).Count -eq 0) {
  Remove-Item -Force $InstallDir
  Write-Host "    removed empty $InstallDir"
}

Step "Done. MetaTrader 5 and your EAs were not touched."
