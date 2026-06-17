import json
from pathlib import Path

from mt5_research_agent.config import (
    AppConfig,
    default_data_dir,
    load_config,
    resolve_config_path,
)


def test_resolve_config_path_uses_env_var(monkeypatch, tmp_path: Path) -> None:
    config_path = tmp_path / "custom.json"
    monkeypatch.setenv("MT5_AGENT_CONFIG", str(config_path))

    resolved = resolve_config_path()

    assert resolved == config_path


def test_resolve_config_path_falls_back_to_per_user_dir(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.delenv("MT5_AGENT_CONFIG", raising=False)
    missing_default = tmp_path / "does-not-exist" / "config.json"

    resolved = resolve_config_path(default_path=missing_default)

    assert resolved == default_data_dir() / "config.json"


def test_load_config_missing_file_returns_defaults(tmp_path: Path) -> None:
    config = load_config(tmp_path / "absent.json")

    # Tolerant load: no crash, sensible per-user absolute data dirs.
    assert isinstance(config, AppConfig)
    assert Path(config.artifacts_dir).is_absolute()
    assert Path(config.results_dir).is_absolute()


def test_load_config_invalid_json_returns_defaults(tmp_path: Path) -> None:
    bad = tmp_path / "config.json"
    bad.write_text("{ not valid json", encoding="utf-8")

    config = load_config(bad)

    assert isinstance(config, AppConfig)
    assert Path(config.artifacts_dir).is_absolute()


def test_load_config_reads_expected_fields(tmp_path: Path) -> None:
    config_path = tmp_path / "config.json"
    payload = {
        "terminal_path": "C:/Program Files/MetaTrader 5/terminal64.exe",
        "portable_mode": True,
        "mt5_window_title_contains": "Strategy Tester",
        "artifacts_dir": "artifacts",
        "results_dir": "results",
        "default_timeout_seconds": 45,
        "shutdown_terminal_after_run": True,
        "report_path_strategy": "terminal_relative_reports",
        "allow_stop_existing_terminal": False,
        "max_parallel_mt5_processes": 1,
        "process_priority": "below_normal",
    }
    config_path.write_text(json.dumps(payload), encoding="utf-8")

    config = load_config(config_path)

    assert config == AppConfig.from_dict(payload)
