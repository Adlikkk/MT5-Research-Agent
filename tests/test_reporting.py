import json
import subprocess
from pathlib import Path

from mt5_research_agent.background_runner import generate_mt5_files, run_task_cli
from mt5_research_agent.reporting import run_explain_decision_command
from mt5_research_agent.result_store import fetch_latest_run_attempt, fetch_run


def _write_terminal_config(tmp_path: Path, monkeypatch) -> Path:
    monkeypatch.setenv("APPDATA", str(tmp_path / "roaming"))
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "local"))
    terminal_path = tmp_path / "terminal64.exe"
    terminal_path.write_text("", encoding="utf-8")
    config_path = tmp_path / "config.json"
    config_path.write_text(
        json.dumps(
            {
                "terminal_path": str(terminal_path),
                "portable_mode": True,
                "mt5_window_title_contains": "MetaTrader",
                "artifacts_dir": str(tmp_path / "artifacts"),
                "results_dir": str(tmp_path / "results"),
                "default_timeout_seconds": 30,
                "shutdown_terminal_after_run": True,
                "report_path_strategy": "terminal_relative_reports",
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("MT5_AGENT_CONFIG", str(config_path))
    return config_path


def _write_task(tmp_path: Path, *, min_profit: float = -999999.0, min_pf: float = 0.0, max_dd: float = 100.0, min_trades: int = 0) -> Path:
    task_path = tmp_path / "US30-SMOKE-0001-FIXED.json"
    task_path.write_text(
        json.dumps(
            {
                "test_id": "US30-SMOKE-0001-FIXED",
                "name": "us30-smoke-0001-fixed",
                "ea": "Advisors\\US30_MultiStrategyLab_M15",
                "symbol": "US30",
                "timeframe": "M15",
                "period_from": "2024.01.01",
                "period_to": "2024.02.01",
                "deposit": 10000,
                "model": "Every tick based on real ticks",
                "inputs": {},
                "acceptance": {
                    "min_profit": min_profit,
                    "min_profit_factor": min_pf,
                    "max_equity_dd_pct": max_dd,
                    "min_trades": min_trades,
                },
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    return task_path


def _fake_process(monkeypatch, pid: int = 4242, returncode: int = 0) -> None:
    class FakeProcess:
        def __init__(self) -> None:
            self.pid = pid
            self.returncode = returncode

        def communicate(self, timeout=None):
            return ("stdout ok", "")

    monkeypatch.setattr(subprocess, "Popen", lambda *args, **kwargs: FakeProcess())
    monkeypatch.setattr(
        "mt5_research_agent.background_runner.mt5_process_status_payload",
        lambda config: {
            "running": False,
            "matching_running": False,
            "configured_terminal_path": config.terminal_path,
            "processes": [],
            "recommended_action": "none",
        },
    )


def test_relaxed_smoke_acceptance_passes_for_realistic_mt5_fixture(tmp_path: Path, monkeypatch) -> None:
    _write_terminal_config(tmp_path, monkeypatch)
    task_path = _write_task(tmp_path)
    _fake_process(monkeypatch)

    files = generate_mt5_files(task_path)
    fixture_path = Path("tests/fixtures/report_mt5_cz_minimal.htm")
    files.report_path.write_text(fixture_path.read_text(encoding="utf-8"), encoding="utf-8")

    result = run_task_cli(str(task_path), timeout_seconds=30)
    run_row = fetch_run("US30-SMOKE-0001-FIXED")

    assert result.status == "PASS"
    assert run_row is not None
    assert run_row["decision_reason"] == "All acceptance rules passed."


def test_missing_acceptance_metrics_are_stored_as_distinct_failure(tmp_path: Path, monkeypatch) -> None:
    _write_terminal_config(tmp_path, monkeypatch)
    task_path = _write_task(tmp_path, min_profit=0, min_pf=1.1, max_dd=18, min_trades=100)
    _fake_process(monkeypatch, pid=4243)

    files = generate_mt5_files(task_path)
    fixture_path = Path("tests/fixtures/report_missing_metrics.htm")
    files.report_path.write_text(fixture_path.read_text(encoding="utf-8"), encoding="utf-8")

    result = run_task_cli(str(task_path), timeout_seconds=30)
    attempt = fetch_latest_run_attempt("US30-SMOKE-0001-FIXED")
    run_row = fetch_run("US30-SMOKE-0001-FIXED")

    assert result.status == "FAIL_WITH_MISSING_METRICS"
    assert attempt is not None
    assert attempt["decision_reason"].startswith("Missing acceptance metrics:")
    assert run_row is not None
    assert run_row["rejection_reason"]
    assert "Metric not found: profit_factor" in run_row["parsed_metrics_payload"]["parser_warnings"]


def test_explain_decision_reports_missing_metrics(tmp_path: Path, monkeypatch, capsys) -> None:
    _write_terminal_config(tmp_path, monkeypatch)
    task_path = _write_task(tmp_path, min_profit=0, min_pf=1.1, max_dd=18, min_trades=100)
    _fake_process(monkeypatch, pid=4244)

    files = generate_mt5_files(task_path)
    fixture_path = Path("tests/fixtures/report_missing_metrics.htm")
    files.report_path.write_text(fixture_path.read_text(encoding="utf-8"), encoding="utf-8")

    run_task_cli(str(task_path), timeout_seconds=30)
    exit_code = run_explain_decision_command("US30-SMOKE-0001-FIXED")
    output = capsys.readouterr().out

    assert exit_code == 0
    assert "final decision: FAIL_WITH_MISSING_METRICS" in output
    assert "missing metrics:" in output
    assert "- profit_factor" in output
