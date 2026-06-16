# Install

## Requirements

- Windows 10 or newer
- Python 3.11+
- MetaTrader 5 already installed locally
- an already-open MT5 terminal for inspection and tester automation phases

## Setup

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install -e .[dev]
Copy-Item config.example.json config.json
```

Edit `config.json` for your workstation:

- `terminal_path`
- `portable_mode`
- `mt5_window_title_contains`
- `artifacts_dir`
- `results_dir`

## First Verification

```powershell
python -m mt5_research_agent version
python -m mt5_research_agent doctor
python -m pytest
```

## Guided installer (optional)

For an isolated install (its own venv, config, and data directories) without
manual venv steps:

```powershell
# Install into %LOCALAPPDATA%\MT5ResearchAgent (no admin required)
powershell -ExecutionPolicy Bypass -File scripts\install.ps1

# Preview what it will do first
powershell -ExecutionPolicy Bypass -File scripts\install.ps1 -DryRun
```

The installer creates a venv, installs the package (registering the
`mt5-research-agent` command), writes a non-clobbering `config.json`, and adds a
Start Menu shortcut (skip with `-NoShortcut`). It never installs or modifies
MetaTrader 5 and never touches your EA source or compiled `.ex5` files.

Uninstall (research data — `config.json` and `data/` — is preserved by default):

```powershell
powershell -ExecutionPolicy Bypass -File scripts\uninstall.ps1
# also delete config + data (asks for confirmation):
powershell -ExecutionPolicy Bypass -File scripts\uninstall.ps1 -RemoveUserData
```

## Desktop UI (optional)

See [DESKTOP_UI.md](DESKTOP_UI.md). In short: `python -m mt5_research_agent serve-api`,
then `cd ui; npm install; npm run dev`.
