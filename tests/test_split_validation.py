from mt5_research_agent.split_validation import (
    build_split_tasks,
    candidate_prefix,
    evaluate_split_row,
    validate_split_experiment_payload,
)
from mt5_research_agent.task import validate_task_payload


def test_validate_split_experiment_payload_accepts_example_shape() -> None:
    spec = validate_split_experiment_payload(
        {
            "name": "gold_split_validation",
            "base_task": "tasks/examples/gold_single_test.json",
            "splits": [
                {"label": "S1_2020_2021", "from": "2020.01.01", "to": "2021.12.31"},
                {"label": "S2_2022_2023", "from": "2022.01.01", "to": "2023.12.31"},
            ],
            "acceptance": {
                "all_splits_profitable": True,
                "min_profit_factor_each_split": 1.05,
                "max_equity_dd_pct_each_split": 20,
                "min_trades_each_split": 50,
            },
        }
    )

    assert spec.name == "gold_split_validation"
    assert spec.splits[0].label == "S1_2020_2021"


def test_build_split_tasks_applies_split_periods_and_ids() -> None:
    spec = validate_split_experiment_payload(
        {
            "name": "gold_split_validation",
            "base_task": "tasks/examples/gold_single_test.json",
            "splits": [
                {"label": "S1_2020_2021", "from": "2020.01.01", "to": "2021.12.31"},
                {"label": "S2_2022_2023", "from": "2022.01.01", "to": "2023.12.31"},
            ],
            "acceptance": {
                "all_splits_profitable": True,
                "min_profit_factor_each_split": 1.05,
                "max_equity_dd_pct_each_split": 20,
                "min_trades_each_split": 50,
            },
        }
    )
    base_task = validate_task_payload(
        {
            "name": "gold_single_test",
            "ea": "GoldEA",
            "symbol": "XAUUSD_DUKA",
            "timeframe": "H1",
            "period_from": "2020.01.01",
            "period_to": "2026.06.01",
            "deposit": 10000,
            "model": "Every tick based on real ticks",
            "inputs": {"TP_R": "2.2"},
            "acceptance": {
                "min_profit": 0,
                "min_profit_factor": 1.1,
                "max_equity_dd_pct": 18,
                "min_trades": 100,
            },
        }
    )

    tasks = build_split_tasks(spec, base_task, "GOLD-0001")

    assert candidate_prefix(spec.name) == "GOLD"
    assert tasks[0]["test_id"] == "GOLD-0001-S01"
    assert tasks[1]["test_id"] == "GOLD-0001-S02"
    assert tasks[0]["period_from"] == "2020.01.01"
    assert tasks[1]["period_to"] == "2023.12.31"


def test_evaluate_split_row_requires_each_split_to_pass() -> None:
    spec = validate_split_experiment_payload(
        {
            "name": "gold_split_validation",
            "base_task": "tasks/examples/gold_single_test.json",
            "splits": [{"label": "S1_2020_2021", "from": "2020.01.01", "to": "2021.12.31"}],
            "acceptance": {
                "all_splits_profitable": True,
                "min_profit_factor_each_split": 1.05,
                "max_equity_dd_pct_each_split": 20,
                "min_trades_each_split": 50,
            },
        }
    )
    row = {
        "parsed_metrics_json": '{"net_profit": 10, "profit_factor": 1.10, "equity_drawdown_percent": 12, "total_trades": 70}'
    }
    failed_row = {
        "parsed_metrics_json": '{"net_profit": -1, "profit_factor": 1.01, "equity_drawdown_percent": 12, "total_trades": 70}'
    }

    passed, reasons = evaluate_split_row(row, spec.acceptance)
    failed, failed_reasons = evaluate_split_row(failed_row, spec.acceptance)

    assert passed is True
    assert reasons == []
    assert failed is False
    assert "SPLIT_NOT_PROFITABLE" in failed_reasons
