# MT5 Research Agent — Desktop UI

A local-first desktop UI (Tauri 2 + React + TypeScript + Vite) for the MT5
Research Agent. It is a **thin client over the localhost HTTP API** — it never
duplicates backend logic and never has a trading path. Start the API first:

```powershell
python -m mt5_research_agent serve-api   # http://127.0.0.1:8765
```

## Screens

Onboarding · Research Composer · Runs · Leaderboard · Reports · EA Lab ·
Settings · Logs. The read screens (Runs, Leaderboard, Reports, Settings, Logs)
work without MT5; the Composer and EA Lab call the safe deterministic endpoints.
Backtests and other MT5-launching actions stay on the explicit CLI by design.

## Develop (browser)

```powershell
cd ui
npm install
npm run dev        # http://localhost:1420, talks to the API at 127.0.0.1:8765
```

Set a different API address from the **Settings** screen (stored in
localStorage). It must stay on localhost.

## Build the web frontend

```powershell
npm run typecheck  # tsc --noEmit
npm run build      # tsc && vite build  ->  dist/
```

This is the part exercised in this repo's verification: `npm install`,
`typecheck`, and `build` all succeed and produce `dist/`.

## Build the desktop app (Tauri)

```powershell
npm run tauri dev      # windowed dev
npm run tauri build    # release bundle
```

Requirements and honest status:

- Needs the Rust toolchain and, on Windows, the WebView2 runtime.
- `bundle.active` is `false` in `src-tauri/tauri.conf.json` until real app icons
  are added (`npm run tauri icon <png>`). Flip it to `true` for a release build.
- The windowed Tauri build and its interactive behavior must be run on a real
  desktop — it cannot be exercised in a headless CI environment, so it is not
  part of the automated verification here. The web frontend build is.
