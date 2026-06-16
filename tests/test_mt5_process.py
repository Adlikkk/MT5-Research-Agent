import json
from pathlib import Path

from mt5_research_agent.config import load_config
from mt5_research_agent.mt5_process import mt5_process_status_payload, stop_mt5_payload


def _write_config(tmp_path: Path, monkeypatch) -> Path:
    monkeypatch.setenv("APPDATA", str(tmp_path / "roaming"))
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "local"))
    terminal_path = tmp_path / "terminal64.exe"
    terminal_path.write_text("", encoding="utf-8")
    config_path = tmp_path / "config.json"
    payload = {
        "terminal_path": str(terminal_path),
        "portable_mode": False,
        "mt5_window_title_contains": "MetaTrader",
        "artifacts_dir": str(tmp_path / "artifacts"),
        "results_dir": str(tmp_path / "results"),
        "default_timeout_seconds": 30,
        "allow_stop_existing_terminal": False,
        "max_parallel_mt5_processes": 1,
        "process_priority": "below_normal",
    }
    config_path.write_text(json.dumps(payload), encoding="utf-8")
    monkeypatch.setenv("MT5_AGENT_CONFIG", str(config_path))
    return config_path


def test_mt5_process_status_with_mocked_process_list(tmp_path: Path, monkeypatch) -> None:
    config = load_config(_write_config(tmp_path, monkeypatch))
    processes = [
        {"pid": 100, "path": config.terminal_path, "command_line": "terminal64.exe"},
        {"pid": 200, "path": str(tmp_path / "other" / "terminal64.exe"), "command_line": "terminal64.exe"},
    ]

    payload = mt5_process_status_payload(config, processes)

    assert payload["running"] is True
    assert payload["matching_running"] is True
    assert any(item["path_matches_config"] for item in payload["processes"])


def test_stop_mt5_dry_run_does_not_stop_anything(tmp_path: Path, monkeypatch) -> None:
    config = load_config(_write_config(tmp_path, monkeypatch))
    stopped: list[int] = []
    processes = [{"pid": 100, "path": config.terminal_path, "command_line": "terminal64.exe"}]

    payload = stop_mt5_payload(
        confirm=False,
        all_processes=False,
        config=config,
        processes=processes,
        stop_fn=lambda pid: stopped.append(pid),
        wait_fn=lambda pids: True,
    )

    assert payload["targets"]
    assert stopped == []
    assert payload["log_path"] == ""


def test_stop_mt5_confirm_only_targets_matching_terminal_path(tmp_path: Path, monkeypatch) -> None:
    config = load_config(_write_config(tmp_path, monkeypatch))
    stopped: list[int] = []
    processes = [
        {"pid": 100, "path": config.terminal_path, "command_line": "terminal64.exe"},
        {"pid": 200, "path": str(tmp_path / "other" / "terminal64.exe"), "command_line": "terminal64.exe"},
    ]

    payload = stop_mt5_payload(
        confirm=True,
        all_processes=False,
        config=config,
        processes=processes,
        stop_fn=lambda pid: stopped.append(pid),
        wait_fn=lambda pids: True,
    )

    assert stopped == [100]
    assert payload["wait_succeeded"] is True
    assert payload["log_path"]
