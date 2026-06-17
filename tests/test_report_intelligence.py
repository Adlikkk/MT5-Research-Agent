from typing import Any

import mt5_research_agent.report_intelligence as ri
from mt5_research_agent.report_intelligence import (
    build_run_analysis,
    build_strategy_board,
    compute_verdict,
    metrics_view,
)


def _row(
    *,
    test_id: str = "T1",
    net_profit: float | None = 2500.0,
    profit_factor: float | None = 1.4,
    equity_drawdown_pct: float | None = 15.0,
    maximal_drawdown: float | None = 800.0,
    total_trades: int | None = 300,
    long_trades: int | None = 160,
    short_trades: int | None = 140,
    average_win: float | None = 50.0,
    average_loss: float | None = -30.0,
    deposit: float = 10000.0,
    run_kind: str = "full_period",
    passed: bool = True,
) -> dict[str, Any]:
    payload = {
        "net_profit": net_profit,
        "profit_factor": profit_factor,
        "equity_drawdown_pct": equity_drawdown_pct,
        "relative_drawdown_pct": equity_drawdown_pct,
        "maximal_drawdown": maximal_drawdown,
        "total_trades": total_trades,
        "long_trades": long_trades,
        "short_trades": short_trades,
        "average_win": average_win,
        "average_loss": average_loss,
        "winrate_pct": 55.0,
        "expected_payoff": 8.3,
        "parser_warnings": [],
    }
    return {
        "test_id": test_id,
        "ea": "DemoEA",
        "symbol": "XAUUSD",
        "timeframe": "H1",
        "date_range": "2020.01.01 - 2024.01.01",
        "model": "Every tick",
        "deposit": deposit,
        "run_kind": run_kind,
        "parsed_metrics_payload": payload,
        "effective_pass_fail": passed,
        "pass_fail": 1 if passed else 0,
        "effective_decision_reason": "All acceptance rules passed." if passed else "",
        "effective_rejection_reason": "" if passed else "MIN_PROFIT_FACTOR",
        "created_at": "2026-06-17T00:00:00Z",
    }


def test_metrics_view_derives_return_and_recovery() -> None:
    m = metrics_view(_row())
    assert m["return_pct"] == 25.0  # 2500 / 10000
    assert m["recovery_factor"] == 3.12  # 2500 / 800, banker's rounding
    assert m["risk_reward"] == 1.67  # 50 / 30


def test_verdict_infra_only_on_zero_trades() -> None:
    v = compute_verdict(metrics_view(_row(total_trades=0)), split="pending")
    assert v["code"] == "INFRA_ONLY"


def test_verdict_reject_on_negative_profit() -> None:
    v = compute_verdict(metrics_view(_row(net_profit=-500.0)), split="pending")
    assert v["code"] == "REJECT"


def test_verdict_reject_on_failed_split() -> None:
    v = compute_verdict(metrics_view(_row()), split="failed")
    assert v["code"] == "REJECT"


def test_strong_run_is_promising_until_split_validated() -> None:
    # PF 1.4, DD 15, 300 trades but no split yet -> PROMISING (not GOOD).
    v = compute_verdict(metrics_view(_row()), split="pending")
    assert v["code"] == "PROMISING"


def test_good_requires_split_validation() -> None:
    v = compute_verdict(metrics_view(_row()), split="passed")
    assert v["code"] == "GOOD"
    assert any("Split validation passed" in r for r in v["reasons"])


def test_weak_on_thin_profit_factor() -> None:
    v = compute_verdict(metrics_view(_row(profit_factor=1.05, total_trades=120)), split="pending")
    assert v["code"] == "WEAK"


def test_analysis_marks_trade_level_unavailable() -> None:
    analysis = build_run_analysis(_row())
    assert analysis["data_available"]["equity_curve"] is False
    assert analysis["data_available"]["weekday_breakdown"] is False
    assert analysis["data_available"]["long_short_counts"] is True
    assert analysis["data_available"]["long_short_pnl"] is False
    assert "Trade-level breakdown unavailable" in analysis["trade_level_note"]
    assert analysis["long_short"]["long_trades"] == 160
    assert analysis["recommended_next_test"]


def test_one_sided_recommends_ablation() -> None:
    analysis = build_run_analysis(_row(long_trades=300, short_trades=0))
    assert "ablation" in analysis["recommended_next_test"].lower()


def test_strategy_board_classifies(monkeypatch) -> None:
    rows = [
        _row(test_id="champ", run_kind="split_validation", passed=True),  # GOOD
        _row(test_id="chall", run_kind="full_period", passed=True),       # PROMISING
        _row(test_id="rej", net_profit=-100.0, passed=False),             # REJECT
        _row(test_id="infra", total_trades=0, passed=True),               # INFRA -> excluded
    ]
    monkeypatch.setattr(ri, "fetch_runs", lambda: rows)
    board = build_strategy_board()
    assert board["champion"]["test_id"] == "champ"
    assert [c["test_id"] for c in board["challengers"]] == ["chall"]
    assert "rej" in [c["test_id"] for c in board["rejected"]]
    # Infra-only run must not appear anywhere on the board.
    everywhere = [board["champion"]["test_id"]] + [
        c["test_id"] for key in ("challengers", "survivors", "rejected") for c in board[key]
    ]
    assert "infra" not in everywhere


def test_report_analysis_unknown_id(monkeypatch) -> None:
    monkeypatch.setattr(ri, "fetch_run", lambda _id: None)
    result = ri.report_analysis("nope")
    assert result["ok"] is False
    assert result["error"] == "TEST_ID_NOT_FOUND"
