// Prevents an extra console window on Windows in release builds.
#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

// Minimal Tauri 2 shell. The window loads the built React frontend (../dist),
// which talks to the localhost MT5 Research Agent API. No backend research logic
// lives here - the shell only launches the bundled backend sidecar and shows the
// web UI.
//
// One-click: the backend is a PyInstaller sidecar bundled with the app, so the
// user does NOT need Python, pip, or `serve-api`. On startup we best-effort spawn
// the sidecar; if that fails we fall back to `python -m mt5_research_agent
// serve-api` (dev machines). The API binds localhost only and never trades live.

use tauri_plugin_shell::ShellExt;

fn main() {
    tauri::Builder::default()
        .plugin(tauri_plugin_shell::init())
        .setup(|app| {
            let handle = app.handle().clone();
            std::thread::spawn(move || {
                match handle.shell().sidecar("mt5-research-agent-backend") {
                    Ok(cmd) => {
                        let _ = cmd.spawn();
                    }
                    Err(_) => {
                        // Dev fallback: use an installed Python engine if present.
                        let python = if cfg!(windows) { "python" } else { "python3" };
                        let _ = std::process::Command::new(python)
                            .args(["-m", "mt5_research_agent", "serve-api"])
                            .spawn();
                    }
                }
            });
            Ok(())
        })
        .run(tauri::generate_context!())
        .expect("error while running the MT5 Research Agent desktop shell");
}
