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


def resolve_config_path(
    env_var_name: str = DEFAULT_CONFIG_ENV_VAR,
    default_path: Path = DEFAULT_CONFIG_PATH,
) -> Path:
    env_value = os.environ.get(env_var_name)
    if env_value:
        return Path(env_value).expanduser()
    return default_path


def load_config(config_path: Path | None = None) -> AppConfig:
    path = config_path or resolve_config_path()
    with path.open("r", encoding="utf-8") as handle:
        data = json.load(handle)
    return AppConfig.from_dict(data)
