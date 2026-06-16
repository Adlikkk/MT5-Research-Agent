import json

from mt5_research_agent.planner import (
    candidate_score,
    failed_parameter_zones,
    filter_planned_combos,
    parameter_value_stats,
    weak_parameter_values,
)
from mt5_research_agent.research_workflow import parse_research_request


def _request(tmp_path):
    request_path = tmp_path / "request.md"
    request_path.write_text(
        "\n".join(
            [
                "# Example",
                "## Goal",
                "Find robust settings.",
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
                "- SL_ATR: 1.7",
                "## Parameters allowed to change",
                "- TP_R: [2.0, 2.1, 2.2]",
                "- SL_ATR: [1.6, 1.7, 1.8]",
                "## Hard limits",
                "- min_profit: 0",
                "- min_profit_factor: 1.1",
                "- max_equity_dd_pct: 18",
                "- min_trades: 100",
                "- max_tests: 9",
                "- stop_after_failures: 3",
                "## Splits required",
                "- top_candidates: 1",
                "- S1: 2020.01.01 -> 2021.12.31",
                "- S2: 2022.01.01 -> 2023.12.31",
                "- all_splits_profitable: true",
                "- min_profit_factor_each_split: 1.05",
                "- max_equity_dd_pct_each_split: 20",
                "- min_trades_each_split: 50",
                "## Stress tests required",
                "- Manual stress",
                "## Ranking rules",
                "- all splits profitable",
                "## Stop rules",
                "- stop_after_failures: 3",
            ]
        ),
        encoding="utf-8",
    )
    return parse_research_request(request_path)


def test_candidate_score_rejects_missing_splits(tmp_path) -> None:
    request = _request(tmp_path)
    full_row = {
        "rejection_reason": "",
        "raw_report_path": "a.htm",
        "parsed_metrics_json": json.dumps({"net_profit": 100, "profit_factor": 1.3, "equity_drawdown_percent": 10, "total_trades": 120}),
    }
    assert candidate_score(request, full_row, []) is None


def test_parameter_stats_detect_weak_and_failed_values(tmp_path) -> None:
    request = _request(tmp_path)
    assessments = [
        type("A", (), {"inputs": {"TP_R": "2.0", "SL_ATR": "1.6"}, "score": None}),
        type("A", (), {"inputs": {"TP_R": "2.0", "SL_ATR": "1.7"}, "score": None}),
        type("A", (), {"inputs": {"TP_R": "2.1", "SL_ATR": "1.7"}, "score": 70.0}),
        type("A", (), {"inputs": {"TP_R": "2.2", "SL_ATR": "1.8"}, "score": 80.0}),
    ]
    stats = parameter_value_stats(assessments, request.parameter_space)
    weak = weak_parameter_values(stats)
    failed = failed_parameter_zones(stats)

    assert "2.0" in weak["TP_R"]
    assert "2.0" in failed["TP_R"]


def test_filter_planned_combos_skips_tested_and_failed_zones(tmp_path) -> None:
    request = _request(tmp_path)
    combos = [
        {"TP_R": "2.0", "SL_ATR": "1.6"},
        {"TP_R": "2.1", "SL_ATR": "1.7"},
        {"TP_R": "2.2", "SL_ATR": "1.8"},
    ]
    assessments = [
        type("A", (), {"inputs": {"TP_R": "2.1", "SL_ATR": "1.7"}}),
    ]
    planned = filter_planned_combos(
        request,
        combos,
        assessments,
        avoid_values={"TP_R": ["2.0"], "SL_ATR": []},
        limit=10,
    )

    assert planned == [{"TP_R": "2.2", "SL_ATR": "1.8"}]
