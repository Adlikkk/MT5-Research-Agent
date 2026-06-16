<#
.SYNOPSIS
  Install the MT5 Research Agent into an isolated virtual environment.

.DESCRIPTION
  Creates a dedicated venv, installs the package into it, sets up the config
  and data directories, and (optionally) creates a Start Menu shortcut.

  Safety:
    - Does NOT require administrator rights.
    - Does NOT install or modify MetaTrader 5.
    - Does NOT touch, move, or delete any EA source or compiled .ex5 files.
    - Preserves any existing config.json and results/artifacts (config-wizard
      is non-clobbering).

.PARAMETER InstallDir
  Target directory. Default: %LOCALAPPDATA%\MT5ResearchAgent

.PARAMETER NoShortcut
  Skip creating the Start Menu shortcut.

.PARAMETER DryRun
  Print the planned actions without changing anything.

.EXAMPLE
  powershell -ExecutionPolicy Bypass -File scripts\install.ps1
#>
[CmdletBinding()]
param(
  [string]$InstallDir = (Join-Path $env:LOCALAPPDATA "MT5ResearchAgent"),
  [switch]$NoShortcut,
  [switch]$DryRun
)

$ErrorActionPreference = "Stop"
$RepoRoot = Split-Path -Parent $PSScriptRoot

function Step($message) { Write-Host "==> $message" -ForegroundColor Cyan }
function Plan($message) { Write-Host "    [dry-run] $message" -ForegroundColor DarkGray }

Step "MT5 Research Agent installer"
Write-Host "    repo:    $RepoRoot"
Write-Host "    install: $InstallDir"

# 1) Python prerequisite (>= 3.11).
$py = Get-Command python -ErrorAction SilentlyContinue
if (-not $py) { throw "Python 3.11+ is required but 'python' was not found on PATH." }
$ver = (& python -c "import sys;print('%d.%d'%sys.version_info[:2])").Trim()
if ([version]$ver -lt [version]"3.11") { throw "Python 3.11+ is required (found $ver)." }
Write-Host "    python:  $ver"

$venv = Join-Path $InstallDir ".venv"
$venvPython = Join-Path $venv "Scripts\python.exe"
$dataDir = Join-Path $InstallDir "data"

if ($DryRun) {
  Plan "create directory $InstallDir"
  Plan "create venv $venv"
  Plan "pip install `"$RepoRoot`" into the venv"
  Plan "config-wizard --artifacts-dir $dataDir\artifacts --results-dir $dataDir\results"
  if (-not $NoShortcut) { Plan "create Start Menu shortcut" }
  Step "Dry run complete. No changes were made."
  return
}

# 2) Directories.
Step "Creating directories"
New-Item -ItemType Directory -Force -Path $InstallDir | Out-Null
New-Item -ItemType Directory -Force -Path $dataDir | Out-Null

# 3) Virtual environment.
Step "Creating virtual environment"
if (-not (Test-Path $venvPython)) { & python -m venv $venv }

# 4) Install the package into the venv.
Step "Installing the package (this downloads Pillow and pywinauto)"
& $venvPython -m pip install --upgrade pip | Out-Null
& $venvPython -m pip install "$RepoRoot"

# 5) Config + data directories (non-clobbering).
Step "Writing config (non-clobbering)"
$cli = Join-Path $venv "Scripts\mt5-research-agent.exe"
$env:MT5_AGENT_CONFIG = Join-Path $InstallDir "config.json"
& $cli config-wizard --artifacts-dir (Join-Path $dataDir "artifacts") --results-dir (Join-Path $dataDir "results")

# 6) Launcher + shortcut.
$launcher = Join-Path $InstallDir "mt5-research-agent.cmd"
@"
@echo off
set "MT5_AGENT_CONFIG=$($env:MT5_AGENT_CONFIG)"
"$cli" %*
"@ | Set-Content -Encoding ASCII $launcher
Write-Host "    launcher: $launcher"

if (-not $NoShortcut) {
  Step "Creating Start Menu shortcut"
  $startMenu = Join-Path $env:APPDATA "Microsoft\Windows\Start Menu\Programs"
  $shortcut = Join-Path $startMenu "MT5 Research Agent.lnk"
  $shell = New-Object -ComObject WScript.Shell
  $link = $shell.CreateShortcut($shortcut)
  $link.TargetPath = "cmd.exe"
  $link.Arguments = "/k `"$launcher`" --help"
  $link.WorkingDirectory = $InstallDir
  $link.Description = "MT5 Research Agent (Strategy Tester research, local only)"
  $link.Save()
  Write-Host "    shortcut: $shortcut"
}

Step "Done."
Write-Host "Next:" -ForegroundColor Green
Write-Host "  `"$launcher`" doctor"
Write-Host "  `"$launcher`" config-wizard   # set your MT5 terminal_path"
Write-Host "Uninstall with: scripts\uninstall.ps1 -InstallDir `"$InstallDir`""
