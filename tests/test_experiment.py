from mt5_research_agent.experiment import (
    build_generated_tasks,
    experiment_prefix,
    validate_experiment_payload,
)
from mt5_research_agent.task import validate_task_payload


def test_validate_experiment_payload_accepts_example_shape() -> None:
    spec = validate_experiment_payload(
        {
            "name": "gold_tp_sl_adx_sweep",
            "base_task": "tasks/examples/gold_single_test.json",
            "matrix": {
                "TP_R": ["2.0", "2.1"],
                "SL_ATR": ["1.6"],
            },
            "limits": {
                "max_tests": 2,
                "stop_after_failures": 1,
            },
        }
    )

    assert spec.name == "gold_tp_sl_adx_sweep"
    assert spec.limits.max_tests == 2


def test_build_generated_tasks_creates_gold_style_ids() -> None:
    spec = validate_experiment_payload(
        {
            "name": "gold_tp_sl_adx_sweep",
            "base_task": "tasks/examples/gold_single_test.json",
            "matrix": {
                "TP_R": ["2.0", "2.1"],
                "SL_ATR": ["1.6"],
            },
            "limits": {
                "max_tests": 10,
                "stop_after_failures": 2,
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
            "inputs": {"TP_R": "2.2", "SL_ATR": "1.7"},
            "acceptance": {
                "min_profit": 0,
                "min_profit_factor": 1.1,
                "max_equity_dd_pct": 18,
                "min_trades": 100,
            },
        }
    )

    tasks = build_generated_tasks(spec, base_task)

    assert experiment_prefix(spec.name) == "GOLD"
    assert tasks[0]["test_id"] == "GOLD-0001"
    assert tasks[1]["test_id"] == "GOLD-0002"
    assert tasks[0]["inputs"]["TP_R"] == "2.0"
    assert tasks[1]["inputs"]["TP_R"] == "2.1"
