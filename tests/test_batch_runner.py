import json
from pathlib import Path

import mt5_research_agent.batch_runner as batch_runner
from mt5_research_agent.batch_runner import (
    discover_batch_tasks,
    run_batch,
    run_batch_status_command,
    run_run_batch_command,
    select_batch_tasks,
)
from mt5_research_agent.run_task import RunTaskResult


def _write_config(tmp_path: Path, monkeypatch) -> Path:
    config_path = tmp_path / "config.json"
    payload = {
        "terminal_path": "",
        "portable_mode": True,
        "mt5_window_title_contains": "MetaTrader",
        "artifacts_dir": str(tmp_path / "artifacts"),
        "results_dir": str(tmp_path / "results"),
        "default_timeout_seconds": 30,
        "shutdown_terminal_after_run": True,
        "report_path_strategy": "terminal_relative_reports",
    }
    config_path.write_text(json.dumps(payload), encoding="utf-8")
    monkeypatch.setenv("MT5_AGENT_CONFIG", str(config_path))
    return config_path


def _task_payload(test_id: str) -> dict:
    return {
        "test_id": test_id,
        "name": test_id.lower(),
        "ea": "GoldEA",
        "symbol": "XAUUSD",
        "timeframe": "H1",
        "period_from": "2024.01.01",
        "period_to": "2024.02.01",
        "deposit": 10000,
        "model": "Every tick based on real ticks",
        "inputs": {"TP_R": "2.0"},
        "acceptance": {
            "min_profit": 0,
            "min_profit_factor": 1.1,
            "max_equity_dd_pct": 18,
            "min_trades": 0,
        },
    }


def _write_tasks(task_dir: Path, test_ids: list[str]) -> None:
    task_dir.mkdir(parents=True, exist_ok=True)
    for test_id in test_ids:
        (task_dir / f"{test_id}.json").write_text(
            json.dumps(_task_payload(test_id), indent=2), encoding="utf-8"
        )


def _ok_result(test_id: str, status: str = "PASS", safety: bool = False) -> RunTaskResult:
    return RunTaskResult(
        exit_code=0 if status in {"PASS", "ok"} else 1,
        status=status,
        test_id=test_id,
        raw_report_path="",
        log_path=f"{test_id}.json",
        screenshot_path="",
        safety_ui_failure=safety,
    )


def test_discover_batch_tasks_skips_files_without_test_id(tmp_path: Path, monkeypatch) -> None:
    _write_config(tmp_path, monkeypatch)
    task_dir = tmp_path / "tasks"
    _write_tasks(task_dir, ["EXP-0002", "EXP-0001"])
    # A base_task.json without a test_id should be ignored.
    no_id = _task_payload("ignored")
    del no_id["test_id"]
    (task_dir / "base_task.json").write_text(json.dumps(no_id), encoding="utf-8")
    (task_dir / "not_json.txt").write_text("nope", encoding="utf-8")

    discovered = discover_batch_tasks(task_dir)

    assert [test_id for test_id, _ in discovered] == ["EXP-0001", "EXP-0002"]


def test_select_batch_tasks_respects_limit_and_skips_completed(tmp_path: Path, monkeypatch) -> None:
    _write_config(tmp_path, monkeypatch)
    task_dir = tmp_path / "tasks"
    _write_tasks(task_dir, ["EXP-0001", "EXP-0002", "EXP-0003", "EXP-0004"])
    discovered = discover_batch_tasks(task_dir)

    monkeypatch.setattr(
        batch_runner,
        "is_task_completed",
        lambda test_id: test_id == "EXP-0001",
    )

    to_run, skipped = select_batch_tasks(discovered, limit=2, rerun=False)

    assert skipped == ["EXP-0001"]
    assert [test_id for test_id, _ in to_run] == ["EXP-0002", "EXP-0003"]


def test_run_batch_runs_eligible_and_writes_summary(tmp_path: Path, monkeypatch) -> None:
    _write_config(tmp_path, monkeypatch)
    task_dir = tmp_path / "tasks"
    _write_tasks(task_dir, ["EXP-0001", "EXP-0002", "EXP-0003"])

    calls: list[str] = []

    def fake_execute(task_path, **kwargs):
        test_id = Path(task_path).stem
        calls.append(test_id)
        return _ok_result(test_id, "PASS" if test_id != "EXP-0002" else "FAIL")

    monkeypatch.setattr(batch_runner, "execute_run_task", fake_execute)
    monkeypatch.setattr(batch_runner, "update_leaderboard_csv", lambda: None)
    monkeypatch.setattr(batch_runner, "update_summary_md", lambda: None)
    monkeypatch.setattr(batch_runner, "is_task_completed", lambda test_id: False)

    result = run_batch(task_dir, limit=3, execution_mode="cli")

    assert calls == ["EXP-0001", "EXP-0002", "EXP-0003"]
    assert result.attempted == 3
    assert result.passed == 2
    assert result.failed == 1
    assert not result.halted
    summary = batch_runner.batch_summary_path().read_text(encoding="utf-8")
    assert "EXP-0002" in summary
    assert "Failed/other: 1" in summary


def test_run_batch_halts_on_infrastructure_failure(tmp_path: Path, monkeypatch) -> None:
    _write_config(tmp_path, monkeypatch)
    task_dir = tmp_path / "tasks"
    _write_tasks(task_dir, ["EXP-0001", "EXP-0002", "EXP-0003"])

    calls: list[str] = []

    def fake_execute(task_path, **kwargs):
        test_id = Path(task_path).stem
        calls.append(test_id)
        if test_id == "EXP-0002":
            return _ok_result(test_id, "PROCESS_FAILED")
        return _ok_result(test_id, "PASS")

    monkeypatch.setattr(batch_runner, "execute_run_task", fake_execute)
    monkeypatch.setattr(batch_runner, "update_leaderboard_csv", lambda: None)
    monkeypatch.setattr(batch_runner, "update_summary_md", lambda: None)
    monkeypatch.setattr(batch_runner, "is_task_completed", lambda test_id: False)

    result = run_batch(task_dir, execution_mode="cli")

    # Should stop after the infrastructure failure and not run EXP-0003.
    assert calls == ["EXP-0001", "EXP-0002"]
    assert result.halted
    assert "PROCESS_FAILED" in result.halt_reason


def test_run_batch_dry_run_does_not_execute(tmp_path: Path, monkeypatch) -> None:
    _write_config(tmp_path, monkeypatch)
    task_dir = tmp_path / "tasks"
    _write_tasks(task_dir, ["EXP-0001", "EXP-0002"])

    def fail_execute(*args, **kwargs):  # pragma: no cover - must not be called
        raise AssertionError("dry run must not execute tasks")

    monkeypatch.setattr(batch_runner, "execute_run_task", fail_execute)
    monkeypatch.setattr(batch_runner, "is_task_completed", lambda test_id: False)

    result = run_batch(task_dir, execution_mode="cli", dry_run=True)

    assert result.dry_run
    assert result.attempted == 0
    assert result.total_discovered == 2


def test_run_batch_command_and_status(tmp_path: Path, monkeypatch, capsys) -> None:
    _write_config(tmp_path, monkeypatch)
    task_dir = tmp_path / "tasks"
    _write_tasks(task_dir, ["EXP-0001"])

    monkeypatch.setattr(
        batch_runner,
        "execute_run_task",
        lambda task_path, **kwargs: _ok_result(Path(task_path).stem, "PASS"),
    )
    monkeypatch.setattr(batch_runner, "update_leaderboard_csv", lambda: None)
    monkeypatch.setattr(batch_runner, "update_summary_md", lambda: None)
    monkeypatch.setattr(batch_runner, "is_task_completed", lambda test_id: False)

    exit_code = run_run_batch_command(
        task_dir=str(task_dir),
        limit=None,
        execution_mode="cli",
        dry_run=False,
        rerun=False,
        allow_gui_clicks=False,
        timeout_seconds=30,
    )
    run_output = capsys.readouterr().out

    status_exit = run_batch_status_command()
    status_output = capsys.readouterr().out

    assert exit_code == 0
    assert "passed: 1" in run_output
    assert status_exit == 0
    assert "attempted: 1" in status_output


def test_run_batch_command_gui_requires_flag(tmp_path: Path, monkeypatch, capsys) -> None:
    _write_config(tmp_path, monkeypatch)
    task_dir = tmp_path / "tasks"
    _write_tasks(task_dir, ["EXP-0001"])

    exit_code = run_run_batch_command(
        task_dir=str(task_dir),
        limit=None,
        execution_mode="gui",
        dry_run=False,
        rerun=False,
        allow_gui_clicks=False,
        timeout_seconds=30,
    )
    output = capsys.readouterr().out

    assert exit_code == 2
    assert "allow-gui-clicks" in output


def test_batch_status_without_run(tmp_path: Path, monkeypatch, capsys) -> None:
    _write_config(tmp_path, monkeypatch)
    exit_code = run_batch_status_command()
    output = capsys.readouterr().out

    assert exit_code == 1
    assert "No batch has been run yet." in output
