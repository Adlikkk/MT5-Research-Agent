# Auto-Update (prepared)

**Status: prepared, not yet enabled in the build.** Auto-update is intentionally
left as an explicit opt-in because it requires a signing keypair (which only you,
the publisher, should hold) and a published release endpoint. The desktop app
builds and installs without it; below is the exact procedure to turn it on.

## Why it is deferred

The Tauri updater verifies update artifacts with **your** private signing key.
Shipping a key in this repo would be unsafe, and end-to-end auto-update cannot be
tested without a real published GitHub Release. So the wiring is documented here
rather than baked into the committed build.

## Enable it (publisher steps)

1. **Generate a signing keypair** (keep the private key secret; never commit it):

   ```powershell
   cd ui
   npm install --save-dev @tauri-apps/cli
   npx tauri signer generate -w "$env:USERPROFILE\.tauri\mt5-research-agent.key"
   ```

2. **Add the updater plugin**:

   ```powershell
   npm install @tauri-apps/plugin-updater
   ```
   and in `src-tauri/Cargo.toml` dependencies: `tauri-plugin-updater = "2"`.

3. **Configure `src-tauri/tauri.conf.json`** with the public key and endpoint:

   ```json
   {
     "plugins": {
       "updater": {
         "active": true,
         "pubkey": "<PUBLIC_KEY_FROM_STEP_1>",
         "endpoints": ["https://github.com/<you>/<repo>/releases/latest/download/latest.json"]
       }
     }
   }
   ```

4. **Sign artifacts at build time** by exporting the private key:

   ```powershell
   $env:TAURI_SIGNING_PRIVATE_KEY = Get-Content "$env:USERPROFILE\.tauri\mt5-research-agent.key" -Raw
   npm run tauri build
   ```

   This produces `*-setup.exe`, `*.sig`, and a `latest.json` to attach to the
   GitHub Release.

5. **Publish** the `.exe`, `.sig`, and `latest.json` on the GitHub Release.

## In-app behavior (when enabled)

- The app checks the endpoint on launch and from Settings → Updates.
- **Updates never interrupt active research.** If a job is running, the app shows:
  *"Update available. Install after the current run?"* and defers the install
  until the queue is idle. The app polls the job queue (`GET /jobs`), so it knows
  when MT5 work is in progress.
- The user always confirms before download/install.

## Without auto-update

Until enabled, distribute new versions by publishing a new NSIS `.exe` on GitHub
Releases; users download and run it (it upgrades in place and preserves config
and data). See [RELEASE.md](RELEASE.md).
