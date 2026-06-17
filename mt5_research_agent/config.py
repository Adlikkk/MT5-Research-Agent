from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path


DEFAULT_CONFIG_ENV_VAR = "MT5_AGENT_CONFIG"
DEFAULT_CONFIG_PATH = Path("config.json")


@dataclass(slots=True)
class AppConfig:
    terminal_path: str = ""
    portable_mode: bool = False
    mt5_window_title_contains: str = "Strategy Tester"
    artifacts_dir: str = "artifacts"
    results_dir: str = "results"
    default_timeout_seconds: int = 30
    shutdown_terminal_after_run: bool = True
    report_path_strategy: str = "terminal_relative_reports"
    allow_stop_existing_terminal: bool = False
    max_parallel_mt5_processes: int = 1
    process_priority: str = "below_normal"

    @classmethod
    def from_dict(cls, data: dict) -> "AppConfig":
        return cls(
            terminal_path=str(data.get("terminal_path", "")),
            portable_mode=bool(data.get("portable_mode", False)),
            mt5_window_title_contains=str(data.get("mt5_window_title_contains", "Strategy Tester")),
            artifacts_dir=str(data.get("artifacts_dir", "artifacts")),
            results_dir=str(data.get("results_dir", "results")),
            default_timeout_seconds=int(data.get("default_timeout_seconds", 30)),
            shutdown_terminal_after_run=bool(data.get("shutdown_terminal_after_run", True)),
            report_path_strategy=str(data.get("report_path_strategy", "terminal_relative_reports")),
            allow_stop_existing_terminal=bool(data.get("allow_stop_existing_terminal", False)),
            max_parallel_mt5_processes=int(data.get("max_parallel_mt5_processes", 1)),
            process_priority=str(data.get("process_priority", "below_normal")),
        )


def default_data_dir() -> Path:
    """Stable per-user data directory for the bundled desktop app.

    The installed app may run from an unpredictable working directory, so config
    and data live here rather than next to ``config.json`` in the CWD.
    """

    base = os.environ.get("LOCALAPPDATA") or os.environ.get("APPDATA")
    if base:
        return Path(base) / "MT5ResearchAgent"
    return Path.home() / ".mt5-research-agent"


def resolve_config_path(
    env_var_name: str = DEFAULT_CONFIG_ENV_VAR,
    default_path: Path = DEFAULT_CONFIG_PATH,
) -> Path:
    env_value = os.environ.get(env_var_name)
    if env_value:
        return Path(env_value).expanduser()
    # Prefer an existing ./config.json (dev / repo workflow); otherwise use the
    # stable per-user location so the bundled app has a consistent home.
    if default_path.exists():
        return default_path
    return default_data_dir() / "config.json"


def _default_app_config() -> AppConfig:
    data_dir = default_data_dir()
    return AppConfig(
        artifacts_dir=str(data_dir / "artifacts"),
        results_dir=str(data_dir / "results"),
    )


def load_config(config_path: Path | None = None) -> AppConfig:
    path = config_path or resolve_config_path()
    try:
        with path.open("r", encoding="utf-8") as handle:
            data = json.load(handle)
    except (FileNotFoundError, OSError, json.JSONDecodeError):
        # Work out of the box: a missing or invalid config yields sensible
        # per-user defaults instead of crashing every endpoint that needs config.
        return _default_app_config()
    if not isinstance(data, dict):
        return _default_app_config()
    return AppConfig.from_dict(data)
