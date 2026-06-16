from pathlib import Path

import pytest

from mt5_research_agent.task import load_task, validate_task_payload


def test_validate_task_payload_accepts_example_shape() -> None:
    task = validate_task_payload(
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

    assert task.name == "gold_single_test"
    assert task.test_id is None
    assert task.inputs["TP_R"] == "2.2"
    assert task.acceptance.min_trades == 100


def test_validate_task_payload_rejects_bad_date() -> None:
    with pytest.raises(ValueError, match="period_from"):
        validate_task_payload(
            {
                "name": "bad",
                "ea": "GoldEA",
                "symbol": "XAUUSD_DUKA",
                "timeframe": "H1",
                "period_from": "2020-01-01",
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


def test_load_task_reads_example_file(tmp_path: Path) -> None:
    task_path = tmp_path / "task.json"
    task_path.write_text(
        """
        {
          "name": "gold_single_test",
          "ea": "GoldEA",
          "symbol": "XAUUSD_DUKA",
          "timeframe": "H1",
          "period_from": "2020.01.01",
          "period_to": "2026.06.01",
          "deposit": 10000,
          "model": "Every tick based on real ticks",
          "inputs": { "TP_R": "2.2" },
          "acceptance": {
            "min_profit": 0,
            "min_profit_factor": 1.1,
            "max_equity_dd_pct": 18,
            "min_trades": 100
          }
        }
        """.strip(),
        encoding="utf-8",
    )

    task = load_task(task_path)

    assert task.symbol == "XAUUSD_DUKA"
