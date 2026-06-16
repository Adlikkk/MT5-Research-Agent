# MT5 Research Agent

**Local Strategy Tester automation for systematic MT5 EA research.**

> ⚠️ **Experimental alpha.** Strategy Tester only. No live trading. No broker
> order placement. No `order_send`. No profitability guarantees.

A local **desktop app** for MetaTrader 5 Strategy Tester research. It runs
backtests on your machine, parses the MT5 reports into structured metrics, ranks
candidates, helps you run parameter sweeps with the MT5 optimizer, and keeps you
in control at every step. Nothing leaves your computer; nothing trades live. A
full CLI is included as the engine / advanced mode.

---

## Screenshots

> Screenshots will be added after the first public desktop build is verified on a
> clean machine. The diagrams in [`docs/`](docs) illustrate the workflow in the
> meantime.

---

## Features

### Desktop App
A minimalist dark workspace (Tauri + React): sidebar · research workspace ·
live inspector. A setup wizard detects your MT5 environment; long backtests run
on a background **job queue** so the UI never freezes.

### Research Workflow
Describe a goal and constraints (target return, max drawdown, min profit factor,
min trades, splits), preview the structured request, run it, and watch live
progress. Robustness via **split validation** is required before any candidate is
called "best" — raw return never wins alone.

### Optimizer
Configure a parameter sweep, preview the grid size and generated `.set`, and run
the MT5 optimizer so **one launch evaluates many combinations**. Passes are
ranked with hard filters first; over-fit-looking passes are kept but ranked low.

### EA Lab
Generate safe-by-default Expert Advisors from a prompt (one position, no
martingale/grid, ATR stops, session/spread filters), compile, smoke-test, version,
revert, and improve via parameter search — all sandboxed away from your own EAs.

### Reports & Leaderboard
Parsed run reports, split-validation reports, and honest final reports ("target
reached / not reached", closest robust candidate, rejected candidates with
reasons). A ranked leaderboard with net profit, profit factor, drawdown, trades,
and validation status.

### Agent / MCP
A localhost HTTP API with an async job queue, plus an MCP server (`serve-mcp`) so
AI agents can inspect, plan, explain, and parse — but never launch MT5 directly.
See [docs/MCP_SETUP.md](docs/MCP_SETUP.md).

### Safety
- **Strategy Tester only.** No live trading, no `order_send`, no Buy/Sell automation.
- **Failed results are preserved**, never hidden or deleted.
- **No profit guarantees.** Backtests are not predictions of future performance.

---

## Quickstart (desktop app)

1. Download `MT5 Research Agent Setup.exe` from the GitHub Releases page.
2. Install and open the app (the bundled backend starts automatically).
3. Run the setup wizard.
4. Select or auto-detect your MT5 terminal.
5. Run the first smoke test.
6. Create a research goal.
7. Start research and watch it live.

The desktop installer bundles the backend — **no Python required** for end users.

## Developer install (CLI engine / advanced mode)

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install -e .[dev]
mt5-research-agent doctor
```

Build the desktop app and installer from source:

```powershell
powershell -ExecutionPolicy Bypass -File scripts\build_backend.ps1   # bundle backend sidecar
cd ui
npm install
npm run tauri build      # produces an NSIS .exe + MSI under src-tauri/target/release/bundle/
```

See [docs/INSTALL.md](docs/INSTALL.md) and [docs/RELEASE.md](docs/RELEASE.md).

---

## Supported / tested

> **Tested on FP Markets MT5.** Designed for local MT5 terminals that support
> Strategy Tester CLI mode. Other broker terminals may require symbol or path
> configuration (symbol suffixes, data-folder location, available history).

## Safety

This project automates the MT5 **Strategy Tester** only. It does not trade live
and is not financial advice.

- No live trading. No `order_send`. No Buy/Sell automation.
- Strategy Tester only; GUI fallback is explicit and guarded.
- Failed runs, parser warnings, and diagnostics are always preserved.
- No profitability guarantees — strategy quality is never implied.

Read [docs/SAFETY.md](docs/SAFETY.md) before running any GUI-affecting command.

## Known limitations

- **Not stable v1** — an experimental alpha; interfaces may change.
- Broker MT5 terminals vary; symbols and paths may need configuration.
- Real-tick backtests are not perfectly repeatable (use `1 minute OHLC` for
  infrastructure smoke tests, every-tick for research-quality runs).
- Desktop packaging should be verified on your own machine (install the `.exe`,
  open the app, complete onboarding).
- Strategy quality / profitability is not guaranteed.
- Some advanced workflows (deep EA source editing, low-level diagnostics, agent
  automation) still use the CLI engine.

---

## Documentation

Full index: [docs/README.md](docs/README.md). Highlights:
[INSTALL](docs/INSTALL.md) ·
[MT5 Setup](docs/MT5_SETUP.md) ·
[Desktop UI](docs/DESKTOP_UI.md) ·
[Execution Modes](docs/EXECUTION_MODES.md) ·
[Optimization](docs/OPTIMIZATION.md) ·
[EA Lab](docs/EA_LAB.md) ·
[CLI Reference](docs/CLI_REFERENCE.md) ·
[MCP Setup](docs/MCP_SETUP.md) ·
[AI Providers](docs/AI_PROVIDERS.md) ·
[Safety](docs/SAFETY.md) ·
[Troubleshooting](docs/TROUBLESHOOTING.md) ·
[Release](docs/RELEASE.md)

## Contributing · Security · License

- [CONTRIBUTING.md](CONTRIBUTING.md) — scope and the non-negotiable safety model.
- [SECURITY.md](SECURITY.md) — supported use and how to report issues.
- [LICENSE](LICENSE) — MIT.

## GitHub topics

`metatrader5` · `mt5` · `strategy-tester` · `backtesting` · `algo-trading` ·
`tauri` · `python` · `mql5`
