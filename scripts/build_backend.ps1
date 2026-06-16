<#
.SYNOPSIS
  Build the standalone backend sidecar executable with PyInstaller.

.DESCRIPTION
  Produces a single self-contained .exe that runs the localhost research API
  with no Python install required. The Tauri desktop app bundles and launches
  this as a sidecar so the product is one-click.

  Output is copied to ui/src-tauri/binaries/ with the Rust target-triple suffix
  Tauri expects for external binaries.

.EXAMPLE
  powershell -ExecutionPolicy Bypass -File scripts\build_backend.ps1
#>
[CmdletBinding()]
param(
  [string]$TargetTriple = "x86_64-pc-windows-msvc"
)

$ErrorActionPreference = "Stop"
$RepoRoot = Split-Path -Parent $PSScriptRoot
Set-Location $RepoRoot

Write-Host "==> Building backend sidecar with PyInstaller" -ForegroundColor Cyan
python -m pip install --quiet pyinstaller | Out-Null

$dist = Join-Path $RepoRoot "build\backend"
python -m PyInstaller `
  --noconfirm --clean --onefile `
  --name mt5-research-agent-backend `
  --distpath $dist `
  --workpath (Join-Path $RepoRoot "build\backend-work") `
  --specpath (Join-Path $RepoRoot "build") `
  --collect-submodules mt5_research_agent `
  --collect-all pywinauto `
  --collect-all comtypes `
  --collect-all PIL `
  mt5_research_agent\_backend_main.py

$built = Join-Path $dist "mt5-research-agent-backend.exe"
if (-not (Test-Path $built)) { throw "PyInstaller did not produce $built" }

$binDir = Join-Path $RepoRoot "ui\src-tauri\binaries"
New-Item -ItemType Directory -Force -Path $binDir | Out-Null
$target = Join-Path $binDir "mt5-research-agent-backend-$TargetTriple.exe"
Copy-Item $built $target -Force

Write-Host "==> Sidecar built: $target" -ForegroundColor Green
Write-Host "    size: $([math]::Round((Get-Item $target).Length/1MB,1)) MB"
