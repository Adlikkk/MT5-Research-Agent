# Desktop UI (Phase 8)

A local-first desktop app (Tauri 2 + React + TypeScript + Vite) under [`ui/`](../ui).
It is a **thin client over the localhost HTTP API** — it never duplicates backend
logic and has no trading path. Full UI guide: [`ui/README.md`](../ui/README.md).

It is the **primary product**; the CLI is the engine / advanced mode.

## Layout

Three columns: **sidebar** (navigation) · **main** (the active screen) · **live
inspector** (the current job's progress, logs, result/decision). The inspector
and Runs/Queue are driven by a polled job list, so they stay live while MT5 work
runs.

## Screens

Dashboard · Setup wizard · Research Workspace · Parameter Editor · Optimizer ·
Runs/Queue · Leaderboard · Reports · EA Lab · Settings.

- **Setup** runs live MT5 detection (terminal/data folder/Experts/Tester/report
  writability/MetaEditor, PASS/WARN/FAIL) and launches a first smoke test **as a
  job**.
- **Research Workspace** takes a goal + editable constraints (target return, max
  drawdown, min PF, min trades, splits) and validates/plans/launches.
- **Parameter Editor** edits EA inputs in a grid and previews the generated `.set`.
- **Optimizer** configures a sweep and previews the grid size + `.set`.
- **Runs/Queue** shows every job (queued/running/done/failed) with live progress
  and cancel.

## Async job model (UI never freezes)

Long MT5 work is submitted to a backend **job queue** (`mt5_research_agent/jobs.py`):
the API returns a `job_id` immediately, a single worker runs jobs FIFO (MT5 is
serial), and the UI polls `GET /jobs/:id` for status/progress/logs. MT5 is never
silently killed or restarted per test; cancellation is cooperative.

## Run it

```powershell
python -m mt5_research_agent serve-api    # API the UI talks to (localhost only)

cd ui
npm install
npm run dev                               # browser dev server at :1420
# or the desktop shell:
npm run tauri dev
```

The API base address is configurable from the Settings screen (localhost only).
The API sends permissive CORS headers for `127.0.0.1`/`localhost` so the browser
dev server and the Tauri webview can call it.

## What is verified here vs. on your machine

Verified in this repo's checks:

- `npm install` (114 packages)
- `npm run typecheck` (strict `tsc --noEmit`, zero errors)
- `npm run build` (`tsc && vite build` → `ui/dist`)
- the built bundle is served and loads, and every endpoint the UI calls
  (`/health`, `/config`, `/runs`, `/leaderboard`, `/reports/:id`, `/ai/status`)
  responds with the expected shape.

**Desktop installer is built:** `npm run tauri build` produces a real **NSIS
`.exe`** and an **MSI** under `ui/src-tauri/target/release/bundle/` (verified;
release Rust compile ~3 min). App icons are committed under
`ui/src-tauri/icons/`. The shell best-effort auto-starts the local API
(`python -m mt5_research_agent serve-api`) on launch, so the installed app has a
backend if the Python engine is installed.

Needs a real desktop (not exercisable headlessly here): launching the windowed
app and clicking through onboarding/research. The build, bundle, and full HTTP
API/job contract are verified; the interactive windowed clickthrough is a
user-machine step.

## Research Session control

The Settings screen has a **Research Session** card: start the configured MT5
terminal once, see session + MT5 process status, and stop it (only the
configured terminal — never unrelated MT5). A "research session running"
indicator shows in the sidebar while it is up. The app does **not** silently
restart MT5 per test: session runs reuse the open terminal (GUI), and large
sweeps use optimizer fast-mode. See [EXECUTION_MODES.md](EXECUTION_MODES.md).

### Close prompt

When the window closes with a research session still active, the desktop shell
intercepts the close (Tauri `onCloseRequested`) and shows a three-way dialog:

- **Stop terminal and exit** — stops *only* the configured research terminal, then closes.
- **Leave terminal running** — closes the app; the terminal stays open.
- **Cancel** — stays open.

MT5 is never silently killed and unrelated terminals are never touched. In a
plain browser (dev mode) this falls back to a `beforeunload` warning.

## Architecture

`ui/src/api/client.ts` is the only place that talks to the backend. Screens use
a small `useAsync` hook for loading/error/empty states. Styling is a hand-built
CSS design system (`ui/src/styles.css`) — clean, dark, minimal — with no heavy
component framework, so the build stays deterministic.
