"""Standalone backend entry for the bundled desktop sidecar.

PyInstaller builds this into a single executable so the Tauri desktop app can
start the local research API **without** the user installing Python or running
pip / ``serve-api`` manually. It only serves the localhost-only API - the same
Strategy-Tester-only safety model as the ``serve-api`` CLI command (no live
trading, no ``order_send``).

Host/port can be overridden with ``MT5_API_HOST`` / ``MT5_API_PORT`` env vars so
the Tauri shell and the bundled backend agree on the address.
"""

from __future__ import annotations

import os
import sys


def main() -> int:
    host = os.environ.get("MT5_API_HOST", "127.0.0.1")
    try:
        port = int(os.environ.get("MT5_API_PORT", "8765"))
    except ValueError:
        port = 8765
    # Imported here so PyInstaller's analysis still pulls the API in, but the
    # heavy import only happens when the backend actually starts.
    from mt5_research_agent.api import run_serve_api_command

    print(f"MT5 Research Agent backend starting on http://{host}:{port}", flush=True)
    return run_serve_api_command(host, port)


if __name__ == "__main__":
    sys.exit(main())
