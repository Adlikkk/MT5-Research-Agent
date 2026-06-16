import json

import mt5_research_agent.research_workflow as research_workflow
from mt5_research_agent.research_workflow import (
    build_experiment_payload,
    build_split_experiment_payload,
    build_task_payload,
    parse_research_request,
    run_create_research_request_command,
    run_split_validate_command,
    run_validate_research_request_command,
    scaffold_research_request,
    write_research_plan,
)


def _full_request_markdown() -> str:
    return "\n".join(
        [
            "# Example",
            "## Goal",
            "Find a robust set.",
            "## EA",
            "GoldEA",
            "## Symbol",
            "XAUUSD_DUKA",
            "## Timeframe",
            "H1",
            "## Date range",
            "2020.01.01 -> 2026.06.01",
            "## Baseline inputs",
            "- TP_R: 2.2",
            "## Parameters allowed to change",
            "- TP_R: [2.0, 2.1]",
            "## Hard limits",
            "- min_profit: 0",
            "- min_profit_factor: 1.1",
            "- max_equity_dd_pct: 18",
            "- min_trades: 100",
            "- max_tests: 2",
            "- stop_after_failures: 1",
            "## Splits required",
            "- top_candidates: 1",
            "- S1: 2020.01.01 -> 2021.12.31",
            "- all_splits_profitable: true",
            "- min_profit_factor_each_split: 1.05",
            "- max_equity_dd_pct_each_split: 20",
            "- min_trades_each_split: 50",
            "## Ranking rules",
            "- all splits profitable",
            "## Stop rules",
            "- stop_after_failures: 1",
        ]
    )


def _write_tmp_config(tmp_path, monkeypatch) -> None:
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


def test_parse_research_request_reads_example_shape(tmp_path) -> None:
    request_path = tmp_path / "example.md"
    request_path.write_text(
        "\n".join(
            [
                "# Example",
                "## Goal",
                "Find a robust set.",
                "## EA",
                "GoldEA",
                "## Symbol",
                "XAUUSD_DUKA",
                "## Timeframe",
                "H1",
                "## Date range",
                "2020.01.01 -> 2026.06.01",
                "## Baseline inputs",
                "- TP_R: 2.2",
                "## Parameters allowed to change",
                "- TP_R: [2.0, 2.1, 2.2]",
                "## Hard limits",
                "- min_profit: 0",
                "- min_profit_factor: 1.1",
                "- max_equity_dd_pct: 18",
                "- min_trades: 100",
                "- max_tests: 3",
                "- stop_after_failures: 2",
                "## Splits required",
                "- top_candidates: 1",
                "- S1: 2020.01.01 -> 2021.12.31",
                "- all_splits_profitable: true",
                "- min_profit_factor_each_split: 1.05",
                "- max_equity_dd_pct_each_split: 20",
                "- min_trades_each_split: 50",
                "## Stress tests required",
                "- Manual spread shock",
                "## Ranking rules",
                "- all splits profitable",
                "## Stop rules",
                "- stop_after_failures: 2",
            ]
        ),
        encoding="utf-8",
    )

    request = parse_research_request(request_path)
    task_payload = build_task_payload(request)
    experiment_payload = build_experiment_payload(request, tmp_path / "base_task.json")
    split_payload = build_split_experiment_payload(request, tmp_path / "base_task.json")

    assert request.todos == []
    assert request.ea == "GoldEA"
    assert request.parameter_space["TP_R"] == ["2.0", "2.1", "2.2"]
    assert task_payload["inputs"]["TP_R"] == "2.2"
    assert experiment_payload["limits"]["max_tests"] == 3
    assert split_payload["acceptance"]["all_splits_profitable"] is True


def test_parse_research_request_collects_todos_for_ambiguity(tmp_path) -> None:
    request_path = tmp_path / "ambiguous.md"
    request_path.write_text(
        "\n".join(
            [
                "# Ambiguous",
                "## Goal",
                "Test something.",
                "## EA",
                "GoldEA",
                "## Symbol",
                "XAUUSD_DUKA",
                "## Timeframe",
                "H1",
                "## Date range",
                "invalid",
                "## Baseline inputs",
                "- TP_R: 2.2",
            ]
        ),
        encoding="utf-8",
    )

    request = parse_research_request(request_path)

    assert request.todos
    assert any("Date range" in item for item in request.todos)


def test_write_research_plan_emits_gold_generated_task(tmp_path, monkeypatch) -> None:
    request_path = tmp_path / "example.md"
    request_path.write_text(
        "\n".join(
            [
                "# Example",
                "## Goal",
                "Find a robust set.",
                "## EA",
                "GoldEA",
                "## Symbol",
                "XAUUSD_DUKA",
                "## Timeframe",
                "H1",
                "## Date range",
                "2020.01.01 -> 2026.06.01",
                "## Baseline inputs",
                "- TP_R: 2.2",
                "## Parameters allowed to change",
                "- TP_R: [2.0, 2.1]",
                "## Hard limits",
                "- min_profit: 0",
                "- min_profit_factor: 1.1",
                "- max_equity_dd_pct: 18",
                "- min_trades: 100",
                "- max_tests: 2",
                "- stop_after_failures: 1",
                "## Splits required",
                "- top_candidates: 1",
                "- S1: 2020.01.01 -> 2021.12.31",
                "- all_splits_profitable: true",
                "- min_profit_factor_each_split: 1.05",
                "- max_equity_dd_pct_each_split: 20",
                "- min_trades_each_split: 50",
                "## Stress tests required",
                "- Manual spread shock",
                "## Ranking rules",
                "- all splits profitable",
                "## Stop rules",
                "- stop_after_failures: 1",
            ]
        ),
        encoding="utf-8",
    )
    config_path = tmp_path / "config.json"
    config_path.write_text(
        '{"terminal_path":"","portable_mode":false,"mt5_window_title_contains":"MetaTrader","artifacts_dir":"'
        + str(tmp_path / "artifacts").replace("\\", "/")
        + '","results_dir":"'
        + str(tmp_path / "results").replace("\\", "/")
        + '","default_timeout_seconds":30}',
        encoding="utf-8",
    )
    monkeypatch.setenv("MT5_AGENT_CONFIG", str(config_path))

    request = parse_research_request(request_path)
    artifacts = write_research_plan(request)

    assert artifacts.generated_task_paths
    assert artifacts.generated_task_paths[0].name == "GOLD-0001.json"


def test_parse_research_request_reads_goal_constraints(tmp_path) -> None:
    request_path = tmp_path / "goal.md"
    request_path.write_text(
        "\n".join(
            [
                "# Goal",
                "## Goal",
                "Reach +250% over 5 years.",
                "## Goal constraints",
                "- target_total_return_pct: 250",
                "- target_period_years: 5",
                "- max_equity_drawdown_pct: 25",
                "- must_validate_splits: true",
                "- max_tests: 120",
                "## EA",
                "GoldEA",
                "## Symbol",
                "XAUUSD",
                "## Timeframe",
                "H1",
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
                "- max_tests: 2",
                "- stop_after_failures: 1",
                "## Splits required",
                "- top_candidates: 1",
                "- S1: 2020.01.01 -> 2021.12.31",
                "- all_splits_profitable: true",
                "- min_profit_factor_each_split: 1.05",
                "- max_equity_dd_pct_each_split: 28",
                "- min_trades_each_split: 50",
                "## Ranking rules",
                "- all splits profitable",
                "## Stop rules",
                "- stop_after_failures: 1",
            ]
        ),
        encoding="utf-8",
    )

    request = parse_research_request(request_path)

    assert request.todos == []
    assert request.goal_constraints is not None
    assert request.goal_constraints.target_total_return_pct == 250.0
    assert request.goal_constraints.max_tests == 120


def test_create_and_validate_research_request(tmp_path, capsys) -> None:
    monkey_cwd = tmp_path
    prompt = monkey_cwd / "prompt.md"
    prompt.write_text("Use my US30 EA and reach +250% over 5 years.", encoding="utf-8")

    import os

    previous = os.getcwd()
    os.chdir(monkey_cwd)
    try:
        scaffold_path = scaffold_research_request(prompt)
        assert scaffold_path.exists()
        text = scaffold_path.read_text(encoding="utf-8")
        assert "## Goal constraints" in text
        assert "US30" in text

        create_exit = run_create_research_request_command(str(prompt))
        # The scaffold is structurally complete (placeholders included), so it
        # validates OK and surfaces the goal constraints for review.
        validate_exit = run_validate_research_request_command(str(scaffold_path))
    finally:
        os.chdir(previous)

    output = capsys.readouterr().out
    assert create_exit == 0
    assert validate_exit == 0
    assert "validation: ok" in output
    assert "target_total_return_pct: 250.0" in output


def test_split_validate_command_uses_candidate_inputs(tmp_path, monkeypatch, capsys) -> None:
    _write_tmp_config(tmp_path, monkeypatch)
    request_path = tmp_path / "request.md"
    request_path.write_text(_full_request_markdown(), encoding="utf-8")

    monkeypatch.setattr(
        research_workflow,
        "fetch_run",
        lambda candidate_id: {
            "test_id": candidate_id,
            "task_name": "example_gold",
            "full_inputs_json": json.dumps({"TP_R": "2.1"}),
        },
    )

    captured: dict = {}

    def fake_run_splits(split_experiment, candidate_task, candidate_id, *, allow_gui_clicks, timeout_seconds):
        captured["inputs"] = candidate_task.inputs
        captured["splits"] = [split.label for split in split_experiment.splits]
        captured["candidate_id"] = candidate_id
        return True

    monkeypatch.setattr(research_workflow, "run_split_validation_for_candidate", fake_run_splits)
    monkeypatch.setattr(research_workflow, "summarize_candidate", lambda candidate_id: tmp_path / "candidate.md")

    exit_code = run_split_validate_command("GOLD-0001", str(request_path))
    output = capsys.readouterr().out

    assert exit_code == 0
    assert captured["inputs"]["TP_R"] == "2.1"
    assert captured["candidate_id"] == "GOLD-0001"
    assert "decision: PASS" in output
