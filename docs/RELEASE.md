# Release Guide

This project follows [Semantic Versioning](https://semver.org/). The package
version lives in `pyproject.toml` and `mt5_research_agent/__init__.py`; keep them
in sync. The first public release is **`v0.1.0-alpha`** — an experimental alpha,
not a stable v1.

## Positioning

> Local MT5 Strategy Tester research automation. Experimental alpha / release
> candidate. Strategy Tester only. No live trading. No order placement. No
> profitability guarantees. Tested on FP Markets MT5.

## Pre-release checklist

Run every check green before tagging:

```powershell
python -m pytest
ruff check .
mypy mt5_research_agent

cd ui
npm install
npm run typecheck
npm run build
cd ..

mt5-research-agent version
mt5-research-agent doctor
mt5-research-agent examples
mt5-research-agent first-smoke --dry-run
mt5-research-agent session-status
```

Real-terminal sanity (optional, needs a local MT5):

```powershell
mt5-research-agent config-wizard
mt5-research-agent session-start
mt5-research-agent session-status
mt5-research-agent session-stop --confirm
```

## Privacy gate (must pass)

```powershell
git status --short
git check-ignore config.json results/ .env ui/node_modules/ ui/dist/
git ls-files --others --exclude-standard   # exactly what would be committed
```

The committable set must contain **no** private paths, API keys, broker account
details, raw MT5 reports, `results/*.sqlite`, or `.ex5` binaries. App icons under
`ui/src-tauri/icons/` and the clearly-marked demo EA source under `examples/` are
the only binary/strategy assets intentionally included.

## Build the desktop installer

The desktop app bundles the Python engine as a standalone PyInstaller sidecar, so
end users need no Python. Build order:

```powershell
# 1) Bundle the backend sidecar (PyInstaller) into ui/src-tauri/binaries/
powershell -ExecutionPolicy Bypass -File scripts\build_backend.ps1

# 2) Build the desktop app + installers (needs Rust + WebView2 + @tauri-apps/cli)
cd ui
npm install
npm install --save-dev @tauri-apps/cli
npm run tauri build
```

### Where artifacts are output

```text
ui/src-tauri/target/release/mt5-research-agent-ui.exe                       # app binary
ui/src-tauri/target/release/bundle/nsis/MT5 Research Agent_<v>_x64-setup.exe # NSIS installer (primary)
ui/src-tauri/target/release/bundle/msi/MT5 Research Agent_<v>_x64_en-US.msi  # MSI (optional)
```

The NSIS `.exe` (~39 MB, includes the bundled backend) is the **primary release
artifact**. The PowerShell installer (`scripts/install.ps1`) remains a developer
fallback only.

### Which files to upload to the GitHub Release

- `MT5 Research Agent_<v>_x64-setup.exe` (NSIS — the main installer)
- `MT5 Research Agent_<v>_x64_en-US.msi` (optional alternative)
- (When auto-update is enabled — see [UPDATES.md](UPDATES.md) — also `*.sig` and `latest.json`.)

### Verify the installer

1. Run the NSIS `.exe` on a clean Windows machine (no Python).
2. Launch the app from the Start Menu; confirm the backend auto-starts (the UI
   connects, no "API offline").
3. Complete the setup wizard, run a first smoke test, start/stop a session.
4. Uninstall and confirm `config.json` and `data/` are preserved.

### Update strategy

Until auto-update is enabled, publish a new NSIS `.exe` per release; it upgrades
in place and preserves user config and data. See [UPDATES.md](UPDATES.md) for the
Tauri auto-update enablement procedure.

## Commit and tag

```powershell
git add .gitignore .env.example README.md CHANGELOG.md LICENSE SECURITY.md CONTRIBUTING.md AGENTS.md pyproject.toml requirements.txt mt5_research_agent tests docs scripts examples research_requests experiments tasks ui .github
git status --short
git commit -m "Initial public alpha release of MT5 Research Agent"
git tag v0.1.0-alpha
```

Do not use `git add -A` unless you have re-proven that ignored/private files are
safe. Do not push until you have reviewed the staged set.

## GitHub release notes template

```text
v0.1.0-alpha — Experimental alpha. Strategy Tester only. No live trading. No
profitability guarantees.

Local MT5 Strategy Tester research automation: CLI research loop, optimizer
fast-mode, report parser, EA Lab, persistent research session, optional AI
tooling and MCP, and a local desktop UI. Tested on FP Markets MT5.
```

Known alpha limitations: see [README.md](../README.md) and
[TROUBLESHOOTING.md](TROUBLESHOOTING.md).
