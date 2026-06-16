"""Persistent research session / MT5 terminal lifecycle.

Keeps one dedicated MT5 research terminal open across a research session instead
of restarting it for every test.

Honest MT5 constraint (the whole reason this module is careful): a background
CLI ``terminal64.exe /config:<ini>`` launch starts its own terminal instance and
cannot be injected into an already-running terminal on the same data folder. So
"one terminal, many tests" reuse is **not** achievable by firing more `/config`
launches at an open terminal. The reliable ways to run many tests without a
per-test restart are:

  1. **Optimizer fast-mode** - one `/config` launch evaluates many parameter
     combinations (see ``optimizer.py``). Best for sweeps.
  2. **GUI execution** against the open session terminal - drive the Strategy
     Tester in the already-open window (no restart). Best for small queues.

This module owns the lifecycle (start / status / stop) of the configured
research terminal and routes batch/research runs honestly. One-shot CLI mode
remains available for smoke/debug.

Safety: only the *configured* research terminal path is ever started or stopped.
Unrelated MT5 terminals are never touched.
"""

from __future__ import annotations

import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from mt5_research_agent.config import AppConfig, load_config
from mt5_research_agent.mt5_process import mt5_process_status_payload, stop_mt5_payload
from mt5_research_agent.result_store import get_results_dir


def session_file_path() -> Path:
    return get_results_dir() / "research_session.json"


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def load_session() -> dict[str, Any] | None:
    path = session_file_path()
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return data if isinstance(data, dict) else None


def save_session(data: dict[str, Any]) -> Path:
    path = session_file_path()
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")
    return path


def clear_session() -> None:
    path = session_file_path()
    if path.exists():
        path.unlink(missing_ok=True)


def _matching_running(config: AppConfig) -> tuple[bool, list[dict[str, Any]]]:
    status = mt5_process_status_payload(config)
    return bool(status.get("matching_running")), list(status.get("processes", []))


def start_session(*, confirm: bool = False, config: AppConfig | None = None) -> dict[str, Any]:
    """Open (or adopt) the configured research terminal and track it.

    - Never starts a terminal at a path other than the configured one.
    - If a matching terminal is already running but is not a tracked session,
      it refuses unless ``confirm`` is set (then it adopts it).
    """

    config = config or load_config()
    if not config.terminal_path:
        return {"ok": False, "error": "No terminal_path configured. Run config-wizard first."}
    terminal = Path(config.terminal_path).expanduser()
    if not terminal.exists():
        return {"ok": False, "error": f"Configured terminal_path does not exist: {terminal}"}

    running, processes = _matching_running(config)
    existing = load_session()

    if running:
        if existing and str(existing.get("status")) == "running":
            return {
                "ok": True,
                "status": "already_running",
                "session": existing,
                "message": "A tracked research session is already running.",
            }
        if not confirm:
            return {
                "ok": False,
                "status": "needs_confirmation",
                "require_confirm": True,
                "processes": processes,
                "message": (
                    "A matching MT5 terminal is already running but is not a tracked session. "
                    "Re-run with --confirm to adopt and manage it, or stop it first."
                ),
            }
        adopted_pid = processes[0].get("pid") if processes else None
        session = {
            "pid": adopted_pid,
            "terminal_path": str(terminal),
            "started_at": _now_iso(),
            "status": "running",
            "mode": "adopted",
        }
        save_session(session)
        return {"ok": True, "status": "adopted", "session": session}

    command: list[str] = [str(terminal)]
    if config.portable_mode:
        command.append("/portable")
    # Launch detached and do NOT wait: this is a long-lived GUI terminal, not a
    # one-shot tester run. No /config is passed, so it just opens the terminal.
    process = subprocess.Popen(command)
    session = {
        "pid": process.pid,
        "terminal_path": str(terminal),
        "started_at": _now_iso(),
        "status": "running",
        "mode": "managed",
        "portable_mode": config.portable_mode,
    }
    save_session(session)
    return {
        "ok": True,
        "status": "started",
        "session": session,
        "message": "Research terminal started. Open the Strategy Tester (open-tester) before GUI session runs.",
    }


def session_status(config: AppConfig | None = None) -> dict[str, Any]:
    config = config or load_config()
    data = load_session()
    running, processes = _matching_running(config)

    # Reconcile: a tracked session whose terminal is gone is marked stopped.
    if data is not None and str(data.get("status")) == "running" and not running:
        data = {**data, "status": "stopped", "stopped_at": _now_iso(), "stopped_reason": "process_not_found"}
        save_session(data)

    return {
        "ok": True,
        "session_active": bool(data and str(data.get("status")) == "running" and running),
        "tracked": data is not None,
        "process_running": running,
        "processes": processes,
        "session": data,
        "configured_terminal_path": config.terminal_path,
    }


def stop_session(*, confirm: bool = False, config: AppConfig | None = None) -> dict[str, Any]:
    config = config or load_config()
    running, processes = _matching_running(config)

    if not running:
        clear_session()
        return {"ok": True, "status": "not_running", "message": "No matching research terminal is running."}

    if not confirm:
        return {
            "ok": False,
            "status": "needs_confirmation",
            "require_confirm": True,
            "processes": processes,
            "message": (
                f"Re-run with --confirm to stop ONLY the configured research terminal "
                f"({config.terminal_path}). Unrelated MT5 terminals are never touched."
            ),
        }

    stop_payload = stop_mt5_payload(confirm=True, all_processes=False, config=config)
    clear_session()
    return {
        "ok": bool(stop_payload.get("wait_succeeded", False)),
        "status": "stopped" if stop_payload.get("wait_succeeded", False) else "stop_failed",
        "stop_action": stop_payload,
    }


# --------------------------------------------------------------------------- #
# CLI command entry points
# --------------------------------------------------------------------------- #
def _print_session_status(payload: dict[str, Any]) -> None:
    session = payload.get("session") or {}
    print(f"session active: {payload.get('session_active')}")
    print(f"terminal process running: {payload.get('process_running')}")
    print(f"configured terminal: {payload.get('configured_terminal_path') or '<none>'}")
    if session:
        print(f"tracked pid: {session.get('pid')}")
        print(f"started at: {session.get('started_at')}")
        print(f"mode: {session.get('mode')}")
        print(f"status: {session.get('status')}")
    else:
        print("no tracked session.")


def run_session_start_command(confirm: bool = False, as_json: bool = False) -> int:
    payload = start_session(confirm=confirm)
    if as_json:
        print(json.dumps(payload, indent=2))
        return 0 if payload.get("ok") else 1
    if not payload.get("ok"):
        print(payload.get("message") or payload.get("error") or "Could not start the research session.")
        return 1
    print(payload.get("message") or f"research session: {payload.get('status')}")
    session = payload.get("session") or {}
    print(f"pid: {session.get('pid')}  terminal: {session.get('terminal_path')}")
    return 0


def run_session_status_command(as_json: bool = False) -> int:
    payload = session_status()
    if as_json:
        print(json.dumps(payload, indent=2))
        return 0
    _print_session_status(payload)
    return 0


def run_session_stop_command(confirm: bool = False, as_json: bool = False) -> int:
    payload = stop_session(confirm=confirm)
    if as_json:
        print(json.dumps(payload, indent=2))
        return 0 if payload.get("ok") else 1
    if not payload.get("ok") and payload.get("require_confirm"):
        print(payload.get("message"))
        return 1
    if not payload.get("ok"):
        print(payload.get("message") or "Could not stop the research session.")
        return 1
    print(payload.get("message") or f"research session: {payload.get('status')}")
    return 0


def require_active_session_or_explain(*, allow_gui_clicks: bool) -> tuple[bool, str]:
    """Gate for ``--session`` runs. Returns (ok_to_run_via_gui, message).

    Honest routing: session reuse of the open terminal is done through GUI
    execution. If GUI clicks are not authorized, we refuse to silently restart
    MT5 per test and point to the reliable alternatives instead.
    """

    status = session_status()
    if not status.get("session_active"):
        return (
            False,
            "No active research session. Start one with `session-start`, or omit --session for one-shot CLI mode.",
        )
    if not allow_gui_clicks:
        return (
            False,
            "Session mode reuses the OPEN research terminal via GUI automation, so it needs --allow-gui-clicks.\n"
            "Reliable alternatives:\n"
            "  - many parameter combinations -> optimizer fast-mode: `run-optimization <spec.json> --run`\n"
            "  - one-shot per test (restarts MT5 each time) -> omit --session\n"
            "MT5 cannot inject a new background /config run into an already-running terminal, so session mode "
            "will not silently restart MT5 per test.",
        )
    return True, "Session mode active: running the queue via GUI against the open research terminal (no restart)."
