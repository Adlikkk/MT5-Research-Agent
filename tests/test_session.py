from __future__ import annotations

import json
from pathlib import Path

import mt5_research_agent.session as session
from mt5_research_agent.session import (
    load_session,
    require_active_session_or_explain,
    session_status,
    start_session,
    stop_session,
)


def _write_config(tmp_path: Path, monkeypatch, *, terminal: str | None = None) -> str:
    terminal_path = terminal if terminal is not None else str(tmp_path / "terminal64.exe")
    if terminal is None:
        Path(terminal_path).write_text("stub", encoding="utf-8")
    config_path = tmp_path / "config.json"
    config_path.write_text(
        json.dumps(
            {
                "terminal_path": terminal_path,
                "portable_mode": True,
                "artifacts_dir": str(tmp_path / "artifacts"),
                "results_dir": str(tmp_path / "results"),
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("MT5_AGENT_CONFIG", str(config_path))
    return terminal_path


def _mock_status(monkeypatch, *, running: bool, pid: int = 4242) -> None:
    processes = [{"pid": pid, "exe": "terminal64.exe"}] if running else []
    monkeypatch.setattr(
        session,
        "mt5_process_status_payload",
        lambda config: {"matching_running": running, "processes": processes},
    )


class _FakeProc:
    def __init__(self) -> None:
        self.pid = 9999


# --------------------------------------------------------------------------- #
# start
# --------------------------------------------------------------------------- #
def test_start_session_launches_when_not_running(tmp_path: Path, monkeypatch) -> None:
    _write_config(tmp_path, monkeypatch)
    _mock_status(monkeypatch, running=False)
    launched: list[list[str]] = []
    monkeypatch.setattr(session.subprocess, "Popen", lambda cmd, **kw: launched.append(cmd) or _FakeProc())

    result = start_session()
    assert result["ok"] is True
    assert result["status"] == "started"
    assert result["session"]["pid"] == 9999
    assert result["session"]["mode"] == "managed"
    # The launch used the configured terminal and did NOT pass a /config (no per-test run).
    assert launched and "/config" not in " ".join(launched[0])
    assert load_session()["status"] == "running"


def test_start_session_refuses_unknown_running_terminal(tmp_path: Path, monkeypatch) -> None:
    _write_config(tmp_path, monkeypatch)
    _mock_status(monkeypatch, running=True)
    monkeypatch.setattr(session.subprocess, "Popen", lambda *a, **k: _FakeProc())

    result = start_session(confirm=False)
    assert result["ok"] is False
    assert result["require_confirm"] is True


def test_start_session_adopts_with_confirm(tmp_path: Path, monkeypatch) -> None:
    _write_config(tmp_path, monkeypatch)
    _mock_status(monkeypatch, running=True, pid=777)

    def fail_popen(*a, **k):  # pragma: no cover - must not launch a second terminal
        raise AssertionError("adopt must not launch a new terminal")

    monkeypatch.setattr(session.subprocess, "Popen", fail_popen)
    result = start_session(confirm=True)
    assert result["ok"] is True
    assert result["status"] == "adopted"
    assert result["session"]["pid"] == 777
    assert result["session"]["mode"] == "adopted"


def test_start_session_missing_terminal_path(tmp_path: Path, monkeypatch) -> None:
    _write_config(tmp_path, monkeypatch, terminal="")
    result = start_session()
    assert result["ok"] is False
    assert "terminal_path" in result["error"]


# --------------------------------------------------------------------------- #
# status
# --------------------------------------------------------------------------- #
def test_session_status_no_session(tmp_path: Path, monkeypatch) -> None:
    _write_config(tmp_path, monkeypatch)
    _mock_status(monkeypatch, running=False)
    status = session_status()
    assert status["session_active"] is False
    assert status["tracked"] is False


def test_session_status_reconciles_dead_session(tmp_path: Path, monkeypatch) -> None:
    _write_config(tmp_path, monkeypatch)
    _mock_status(monkeypatch, running=False)
    session.save_session({"pid": 1, "terminal_path": "x", "started_at": "t", "status": "running", "mode": "managed"})
    status = session_status()
    # Terminal is gone, so the tracked session is reconciled to stopped.
    assert status["session_active"] is False
    assert load_session()["status"] == "stopped"


# --------------------------------------------------------------------------- #
# stop
# --------------------------------------------------------------------------- #
def test_stop_session_requires_confirm(tmp_path: Path, monkeypatch) -> None:
    _write_config(tmp_path, monkeypatch)
    _mock_status(monkeypatch, running=True)
    result = stop_session(confirm=False)
    assert result["ok"] is False
    assert result["require_confirm"] is True


def test_stop_session_stops_only_configured_terminal(tmp_path: Path, monkeypatch) -> None:
    _write_config(tmp_path, monkeypatch)
    _mock_status(monkeypatch, running=True)
    calls: list[dict] = []

    def fake_stop(*, confirm, all_processes, config):
        calls.append({"confirm": confirm, "all_processes": all_processes})
        return {"wait_succeeded": True}

    monkeypatch.setattr(session, "stop_mt5_payload", fake_stop)
    result = stop_session(confirm=True)
    assert result["ok"] is True
    assert result["status"] == "stopped"
    # Critically, never targets unrelated terminals.
    assert calls and calls[0]["all_processes"] is False
    assert load_session() is None


def test_stop_session_not_running_clears(tmp_path: Path, monkeypatch) -> None:
    _write_config(tmp_path, monkeypatch)
    _mock_status(monkeypatch, running=False)
    result = stop_session(confirm=True)
    assert result["ok"] is True
    assert result["status"] == "not_running"


# --------------------------------------------------------------------------- #
# --session routing gate
# --------------------------------------------------------------------------- #
def test_require_session_no_active(tmp_path: Path, monkeypatch) -> None:
    _write_config(tmp_path, monkeypatch)
    _mock_status(monkeypatch, running=False)
    ok, message = require_active_session_or_explain(allow_gui_clicks=True)
    assert ok is False
    assert "session-start" in message


def test_require_session_active_needs_gui(tmp_path: Path, monkeypatch) -> None:
    _write_config(tmp_path, monkeypatch)
    _mock_status(monkeypatch, running=True)
    session.save_session({"pid": 1, "terminal_path": "x", "started_at": "t", "status": "running", "mode": "managed"})
    ok, message = require_active_session_or_explain(allow_gui_clicks=False)
    assert ok is False
    # Honest fallback guidance.
    assert "optimizer fast-mode" in message
    assert "run-optimization" in message


def test_require_session_active_with_gui(tmp_path: Path, monkeypatch) -> None:
    _write_config(tmp_path, monkeypatch)
    _mock_status(monkeypatch, running=True)
    session.save_session({"pid": 1, "terminal_path": "x", "started_at": "t", "status": "running", "mode": "managed"})
    ok, message = require_active_session_or_explain(allow_gui_clicks=True)
    assert ok is True
    assert "no restart" in message
