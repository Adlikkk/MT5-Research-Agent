import json
from pathlib import Path

import mt5_research_agent.goal_seeker as goal_seeker
from mt5_research_agent.goal import ResearchGoal
from mt5_research_agent.goal_seeker import (
    CandidateGoalView,
    candidate_return_pct,
    meets_raw_goal,
    run_final_report_command,
    run_goal_seek,
    select_best_robust,
    select_closest_raw,
)
from mt5_research_agent.run_task import RunTaskResult


def _write_config(tmp_path: Path, monkeypatch) -> None:
    config_path = tmp_path / "config.json"
    config_path.write_text(
        json.dumps(
            {
                "terminal_path": "",
                "portable_mode": False,
                "mt5_window_title_contains": "MetaTrader",
                "artifacts_dir": str(tmp_path / "artifacts"),
                "results_dir": str(tmp_path / "results"),
                "default_timeout_seconds": 30,
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("MT5_AGENT_CONFIG", str(config_path))


def _row(test_id: str, net_profit: float, pf: float, dd: float, trades: int, deposit: float = 10000) -> dict:
    return {
        "test_id": test_id,
        "task_name": "us30_goal",
        "deposit": deposit,
        "full_inputs_json": json.dumps({"TP_R": "2.0"}),
        "parsed_metrics_json": json.dumps(
            {
                "net_profit": net_profit,
                "profit_factor": pf,
                "equity_drawdown_pct": dd,
                "total_trades": trades,
            }
        ),
    }


def test_candidate_return_pct() -> None:
    assert candidate_return_pct(_row("A", 25000, 1.5, 20, 300)) == 250.0
    assert candidate_return_pct({"parsed_metrics_json": "{}", "deposit": 10000}) is None


def test_meets_raw_goal_pass_and_fail() -> None:
    goal = ResearchGoal(
        target_total_return_pct=250,
        max_equity_drawdown_pct=25,
        min_profit_factor=1.2,
        min_trades=250,
    )
    passed, reasons = meets_raw_goal(_row("A", 25000, 1.5, 20, 300), goal)
    assert passed
    assert reasons == []

    failed, fail_reasons = meets_raw_goal(_row("B", 5000, 1.0, 40, 100), goal)
    assert not failed
    assert "BELOW_TARGET_RETURN" in fail_reasons
    assert "EXCEEDS_MAX_DRAWDOWN" in fail_reasons
    assert "BELOW_MIN_PROFIT_FACTOR" in fail_reasons
    assert "BELOW_MIN_TRADES" in fail_reasons


def _view(test_id: str, return_pct: float, robust: bool, splits) -> CandidateGoalView:
    return CandidateGoalView(
        test_id=test_id,
        task_name="t",
        inputs={},
        return_pct=return_pct,
        profit_factor=1.3,
        drawdown_pct=10,
        total_trades=300,
        meets_raw_goal=robust,
        raw_reasons=[] if robust else ["BELOW_TARGET_RETURN"],
        splits_validated=splits,
        is_robust=robust and splits is True,
    )


def test_select_best_robust_and_closest_raw() -> None:
    views = [
        _view("A", 300, robust=True, splits=True),
        _view("B", 400, robust=True, splits=False),
        _view("C", 500, robust=False, splits=None),
    ]
    best = select_best_robust(views)
    closest = select_closest_raw(views)
    assert best is not None and best.test_id == "A"
    assert closest is not None and closest.test_id == "C"


def test_select_best_robust_none_when_no_robust() -> None:
    views = [_view("C", 500, robust=False, splits=None)]
    assert select_best_robust(views) is None


def _full_request(tmp_path: Path) -> Path:
    request_path = tmp_path / "us30_goal.md"
    request_path.write_text(
        "\n".join(
            [
                "# US30 Goal",
                "## Goal",
                "Reach +250% over 5 years.",
                "## Goal constraints",
                "- target_total_return_pct: 250",
                "- max_equity_drawdown_pct: 25",
                "- min_profit_factor: 1.2",
                "- min_trades: 100",
                "- must_validate_splits: true",
                "- max_tests: 4",
                "## EA",
                "US30EA",
                "## Symbol",
                "US30",
                "## Timeframe",
                "M15",
                "## Date range",
                "2020.01.01 -> 2025.01.01",
                "## Baseline inputs",
                "- TP_R: 2.0",
                "## Parameters allowed to change",
                "- TP_R: [2.0, 2.1]",
                "## Hard limits",
                "- min_profit: 0",
                "- min_profit_factor: 1.1",
                "- max_equity_dd_pct: 25",
                "- min_trades: 100",
                "- max_tests: 4",
                "- stop_after_failures: 2",
                "## Splits required",
                "- top_candidates: 1",
                "- S1: 2020.01.01 -> 2022.12.31",
                "- all_splits_profitable: true",
                "- min_profit_factor_each_split: 1.05",
                "- max_equity_dd_pct_each_split: 28",
                "- min_trades_each_split: 50",
                "## Ranking rules",
                "- all splits profitable",
                "## Stop rules",
                "- stop_after_failures: 2",
            ]
        ),
        encoding="utf-8",
    )
    return request_path


def test_run_goal_seek_reaches_target_with_mocked_runs(tmp_path: Path, monkeypatch) -> None:
    _write_config(tmp_path, monkeypatch)
    request_path = _full_request(tmp_path)

    monkeypatch.setattr(
        goal_seeker,
        "execute_run_task",
        lambda task_path, **kwargs: RunTaskResult(0, "PASS", Path(task_path).stem, "", "", "", False),
    )
    monkeypatch.setattr(goal_seeker, "update_leaderboard_csv", lambda: None)
    monkeypatch.setattr(goal_seeker, "update_summary_md", lambda: None)
    monkeypatch.setattr(
        goal_seeker,
        "run_split_validation_for_candidate",
        lambda *args, **kwargs: True,
    )

    # First view set: a raw-goal candidate awaiting split validation.
    # Second/third: the same candidate now robust (splits validated).
    pending = _view("GOAL-0001", 300, robust=True, splits=None)
    robust = _view("GOAL-0001", 300, robust=True, splits=True)
    sequence = [[pending], [robust], [robust]]

    def fake_views(request, goal):
        return sequence.pop(0) if sequence else [robust]

    monkeypatch.setattr(goal_seeker, "build_candidate_views", fake_views)

    result = run_goal_seek(str(request_path), max_rounds=1)

    assert result.target_reached
    assert result.best_robust_id == "GOAL-0001"
    assert result.stop_reason == "target robustly reached"
    assert Path(result.report_path).exists()
    report = Path(result.report_path).read_text(encoding="utf-8")
    assert "Target robustly reached." in report


def test_run_final_report_command_reports_not_reached(tmp_path: Path, monkeypatch, capsys) -> None:
    _write_config(tmp_path, monkeypatch)
    request_path = _full_request(tmp_path)

    # No robust candidate; closest raw is below the target return.
    monkeypatch.setattr(
        goal_seeker,
        "build_candidate_views",
        lambda request, goal: [_view("GOAL-0002", 120, robust=False, splits=None)],
    )

    exit_code = run_final_report_command(str(request_path))
    output = capsys.readouterr().out

    assert exit_code == 0
    assert "target reached: False" in output
    report_path = goal_seeker.goal_report_path("us30_goal")
    report = report_path.read_text(encoding="utf-8")
    assert "Target not robustly reached." in report
    assert "Closest raw candidate:" in report
    assert "Next suggested research direction:" in report
