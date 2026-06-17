# Changelog

All notable changes to the MT5 Research Agent are documented here. This project
adheres to [Semantic Versioning](https://semver.org/).

## [0.1.1-alpha] - 2026-06-17

Product-polish and strategy-intelligence release. No engine/safety changes —
still Strategy Tester only, no live trading, no `order_send`.

### API reliability (fixes "Failed to fetch")
- **Tolerant config**: `load_config` now returns sensible per-user defaults
  (`%LOCALAPPDATA%\MT5ResearchAgent`) instead of raising when `config.json` is
  missing or malformed, so the bundled app works on first launch.
- **Handler safety net**: the HTTP handler wraps every request in try/except and
  always returns JSON (500 on error) — an exception can no longer reset the
  connection and surface as an opaque `Failed to fetch`.
- **Resilient UI client**: one shared client with typed `ApiError`
  (offline/http/parse), auto-retry on network failure, and a "Starting backend…"
  state. Screens use an `AsyncBoundary` for friendly loading/empty/error states.

### Desktop UI redesign
- New **app shell**: compact top bar with live status pills (API / MT5 / Session
  / Jobs / Update), collapsible icon sidebar (sections), collapsible inspector
  with a live activity stream + elapsed clock.
- **Agent tab** (primary): plain-language goal -> editable plan (goal chips) ->
  start research. New `POST /agent/parse` endpoint.
- Polished Dashboard (latest-test card, quick actions, run heatmap), Setup,
  grouped Parameter editor, segmented EA Lab, and useful empty states everywhere.

### Strategy intelligence
- **Verdict engine** (`report_intelligence.py`): deterministic
  GOOD/PROMISING/WEAK/REJECT/INFRA_ONLY with reasons; GOOD requires split
  validation (profit alone never qualifies a candidate).
- **Advanced Report** screen: header, verdict/confidence, metric cards, target
  bars, long/short counts, analysis, recommended next test. Trade-level
  breakdowns (equity curve, weekday/session) are shown as *unavailable* rather
  than faked.
- **Strategy Board** (replaces Leaderboard): champion / challenger / survivor /
  rejected. New `GET /latest-run`, `GET /strategy-board`,
  `GET /reports/:id/analysis`.

## [0.1.0-alpha] - 2026-06-15

First public **alpha**. Local MT5 Strategy Tester research automation. Tested on
FP Markets MT5; should work with other MT5 terminals after configuration. Not a
stable release — interfaces may change.

### One-click desktop product
- **Bundled backend sidecar**: the Python engine is packaged as a standalone
  PyInstaller executable (`scripts/build_backend.ps1`) and bundled with the Tauri
  app via `externalBin`. The shell auto-starts it on launch (falls back to a local
  Python engine in dev). No `pip install` / `serve-api` needed — the NSIS
  installer (~39 MB) includes everything.
- **In-app MT5 config**: `GET /detect-terminal`, `POST /config/save`, and a
  Settings card to auto-detect and save the terminal path — first setup needs no CLI.
- **Deep research from the UI**: a `research` job runs the goal-seek/run-research
  flow as a background job (live progress, results to Leaderboard/Reports).
- **MCP setup**: `docs/MCP_SETUP.md` (Claude Desktop / Cursor configs, tool list,
  safety) and `serve-mcp --selfcheck` health command.
- **Auto-update prepared**: `docs/UPDATES.md` documents the full enable procedure
  (signing key, updater plugin, endpoint, "install after current run" guard).
  Deferred from the build until a publisher key + release endpoint exist.

### App-first desktop product
- **Async job queue** (`jobs.py`): long MT5 work runs on a background worker;
  submit returns immediately and the UI polls status/progress/logs so it never
  freezes. Cooperative cancel; MT5 is never force-killed mid-write.
- **App-first API**: `GET /detect`, `GET /eas`, `POST /set-preview`,
  `POST /optimizer/preview`, and a jobs CRUD (`POST/GET /jobs`, `GET /jobs/:id`,
  `POST /jobs/:id/cancel`).
- **App-first UI**: three-column workspace (sidebar · main · live inspector) with
  Dashboard, Setup wizard (live MT5 detection + first smoke as a job), Research
  Workspace (goal + editable constraints), Parameter Editor (`.set` preview),
  Optimizer (grid preview), and a live Runs/Queue. The CLI is now the engine /
  advanced mode.
- **Desktop installer**: `npm run tauri build` produces a real **NSIS `.exe`** and
  MSI; the shell best-effort auto-starts the local API on launch.

### Release-candidate hardening
- Desktop: native Tauri close prompt (three-way "Stop terminal and exit / Leave
  running / Cancel") that stops only the configured terminal; generated and
  committed app icons; `cargo check` compiles the Tauri shell and `bundle.active`
  is enabled.
- `config-wizard` now detects and reports (PASS/WARN) the terminal data folder,
  `MQL5\Experts`, `MQL5\Profiles\Tester`, report-path writability, and MetaEditor.
- `uninstall.ps1` accepts an explicit `-PreserveUserData` flag (preserve is the
  default). Added `docs/RELEASE.md`.

### MT5 lifecycle / persistent research session
- New `session-start` / `session-status` / `session-stop` to keep one configured
  research terminal open across a session (stops only the configured terminal,
  never unrelated MT5). `run-batch --session` / `run-research --session` reuse
  the open terminal via GUI rather than restarting MT5 per test, with honest
  fallback to optimizer fast-mode or one-shot when GUI reuse isn't authorized.
- `first-smoke` now defaults to the fast, deterministic `1 minute OHLC` model
  (infrastructure validation) and supports `--dry-run` and an optional `--ea`.
- Desktop UI: a Research Session control (start/status/stop + process state), a
  sidebar "session running" indicator, and an on-close warning. API gained
  `GET /session`, `GET /mt5-process-status`, `POST /session/start|stop`.

### Public release hardening
- Beginner CLI commands: `examples`, `first-smoke`, `open-report`,
  `open-artifacts`.
- `doctor` now reports **PASS/WARN/FAIL** with an overall status and a `--json`
  mode for agents (a missing terminal is a WARN, not a hard FAIL).
- Privacy: example config and docs use neutral values (no broker/personal
  names); `.gitignore` also excludes `*.ex5`, `*.sqlite`, `*.db`, and the private
  build spec; added `.env.example` for optional AI keys.

### Added
- **Efficient optimization mode (Phase 6).** Single-launch MT5 optimizer:
  generate `Optimization=`/`OptimizationCriterion=` ini and `name=v||start||step||stop||Y`
  set files, count the grid, and parse + robustness-rank the optimization
  report (`.xml`). Commands: `plan-optimization`, `run-optimization`,
  `parse-optimization`, `optimization-spec-from-request`, `optimization-status`.
  See `docs/OPTIMIZATION.md`.
- **AI provider system (section 8).** Optional, off by default. OpenAI,
  Anthropic, OpenRouter, Groq, Ollama, and custom OpenAI-compatible endpoints.
  API keys are read from environment variables, never stored. Budgeted and
  ledgered. Commands: `ai-status`, `ai-config`, `ai-complete`. See
  `docs/AI_PROVIDERS.md`.
- **MCP server (Phase 7).** `serve-mcp` exposes the safe, non-destructive tool
  surface over stdio JSON-RPC. MT5-launching tools stay CLI-only. See
  `docs/MCP_SERVER.md`.
- **Desktop UI (Phase 8).** Tauri 2 + React + TypeScript app in `ui/` — a thin
  client over the localhost API with eight screens. See `docs/DESKTOP_UI.md`.
- **Local HTTP API** gained `/ai/status`, `/optimizations/:id`, and CORS headers
  for the localhost desktop UI.
- **Installer / uninstaller (Phase 9).** `scripts/install.ps1` and
  `scripts/uninstall.ps1` (no admin, never touches MT5 or EAs, preserves user
  data), plus a `mt5-research-agent` console entry point.

### Changed
- README, CLI reference, and docs index updated for the new phases.

### Safety
- Unchanged and non-negotiable: Strategy Tester only, no `order_send`, no live
  trading, failed runs are never hidden, and robustness (split validation) is
  required before any candidate is called "best."

## [0.1.0]
- Core background CLI research loop (BG-1…BG-3F), small batch runner, research
  request / goal planner, split validation, goal-seeking loop, EA Lab, the
  localhost HTTP API, and maintenance commands.
