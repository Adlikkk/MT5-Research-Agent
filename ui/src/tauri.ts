// Tauri desktop-shell helpers. Everything here is guarded so the same build runs
// unchanged in a plain browser (where the Tauri runtime is absent).

type CloseRequestedEvent = { preventDefault: () => void };
type TauriWindow = {
  onCloseRequested: (handler: (event: CloseRequestedEvent) => void) => Promise<() => void>;
  destroy: () => Promise<void>;
};

export function isTauri(): boolean {
  return typeof window !== "undefined" && "__TAURI_INTERNALS__" in window;
}

let cachedWindow: TauriWindow | null = null;

async function currentWindow(): Promise<TauriWindow | null> {
  if (!isTauri()) {
    return null;
  }
  if (cachedWindow) {
    return cachedWindow;
  }
  // Dynamic import so a plain browser build never loads the Tauri module.
  const mod = (await import("@tauri-apps/api/window")) as {
    getCurrentWindow: () => TauriWindow;
  };
  cachedWindow = mod.getCurrentWindow();
  return cachedWindow;
}

/**
 * Intercept the native window close. When ``shouldPrompt`` returns true the
 * close is cancelled and ``onPrompt`` runs (so the app can show its own
 * three-way "Stop terminal / Leave running / Cancel" dialog). Returns an
 * unlisten function; a no-op in the browser.
 */
export async function registerCloseGuard(
  shouldPrompt: () => boolean,
  onPrompt: () => void,
): Promise<() => void> {
  const win = await currentWindow();
  if (!win) {
    return () => {};
  }
  return win.onCloseRequested((event) => {
    if (shouldPrompt()) {
      event.preventDefault();
      onPrompt();
    }
  });
}

/** Force the desktop window to close, bypassing the close-requested guard. */
export async function destroyWindow(): Promise<void> {
  const win = await currentWindow();
  if (win) {
    await win.destroy();
  }
}
