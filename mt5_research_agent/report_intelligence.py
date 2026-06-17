"""Deterministic report intelligence: verdicts, analysis, and strategy board.

This turns the *summary* metrics the report parser already extracts into a human
verdict (GOOD / PROMISING / WEAK / REJECT / INFRA ONLY), an explanation of why,
and a champion/challenger/survivor/rejected classification across stored runs.

It is intentionally **deterministic and honest**:

* No profitability is ever promised.
* A single full-period backtest is capped at PROMISING — GOOD requires split
  validation, because profit alone never qualifies a candidate as robust.
* Analytics that need trade-level deal data (equity curve, weekday/monthly/
  session, per-side P&L) are reported as *unavailable* rather than fabricated.
  The MT5 HTML summary the parser reads simply does not contain them.
"""

from __future__ import annotations

from typing import Any

from mt5_research_agent.result_store import fetch_latest_run, fetch_run, fetch_runs


VERDICT_LABELS = {
    "GOOD": "Good",
    "PROMISING": "Promising",
    "WEAK": "Weak",
    "REJECT": "Reject",
    "INFRA_ONLY": "Infra only",
}

# What the MT5 HTML summary report can and cannot tell us. These flags drive the
# UI so it never fakes a chart it has no data for.
DATA_CAPABILITIES = {
    "summary_metrics": True,
    "long_short_counts": True,
    "long_short_pnl": False,
    "equity_curve": False,
    "drawdown_curve": False,
    "monthly_breakdown": False,
    "weekday_breakdown": False,
    "session_breakdown": False,
}

TRADE_LEVEL_UNAVAILABLE_NOTE = (
    "Trade-level breakdown unavailable for this report. Enable/export detailed "
    "deals to unlock weekday/session/long-short P&L analysis."
)


def _num(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    return None


def metrics_view(row: dict[str, Any]) -> dict[str, Any]:
    """Flatten a stored-run row into the numbers the verdict engine needs."""

    payload = row.get("parsed_metrics_payload") or {}
    normalized = payload.get("normalized_metrics") if isinstance(payload, dict) else {}

    def pick(key: str) -> float | None:
        if isinstance(payload, dict) and key in payload:
            value = _num(payload.get(key))
            if value is not None:
                return value
        if isinstance(normalized, dict):
            return _num(normalized.get(key))
        return None

    net_profit = pick("net_profit")
    profit_factor = pick("profit_factor")
    drawdown_pct = pick("equity_drawdown_pct")
    if drawdown_pct is None:
        drawdown_pct = pick("relative_drawdown_pct")
    maximal_drawdown = pick("maximal_drawdown")
    total_trades = pick("total_trades")
    average_win = pick("average_win")
    average_loss = pick("average_loss")
    deposit = _num(row.get("deposit")) or 0.0

    return_pct = (net_profit / deposit * 100.0) if (net_profit is not None and deposit) else None
    recovery_factor: float | None = None
    if net_profit is not None and maximal_drawdown is not None and maximal_drawdown != 0:
        recovery_factor = net_profit / abs(maximal_drawdown)
    risk_reward: float | None = None
    if average_win is not None and average_loss is not None and average_loss != 0:
        risk_reward = average_win / abs(average_loss)

    return {
        "net_profit": net_profit,
        "return_pct": _round(return_pct),
        "profit_factor": profit_factor,
        "drawdown_pct": drawdown_pct,
        "recovery_factor": _round(recovery_factor),
        "expected_payoff": pick("expected_payoff"),
        "total_trades": int(total_trades) if total_trades is not None else None,
        "winrate_pct": pick("winrate_pct"),
        "average_win": average_win,
        "average_loss": average_loss,
        "risk_reward": _round(risk_reward),
        "long_trades": _int(pick("long_trades")),
        "short_trades": _int(pick("short_trades")),
    }


def _round(value: float | None, digits: int = 2) -> float | None:
    return round(value, digits) if value is not None else None


def _int(value: float | None) -> int | None:
    return int(value) if value is not None else None


def split_status(row: dict[str, Any]) -> str:
    """passed | failed | pending — how far split validation has gotten.

    A plain full-period run is ``pending`` (not yet validated), which deliberately
    caps its verdict at PROMISING.
    """

    run_kind = str(row.get("run_kind", "") or "")
    if "split" in run_kind:
        return "passed" if row.get("effective_pass_fail", row.get("pass_fail")) else "failed"
    return "pending"


# ── Verdict engine ───────────────────────────────────────────────────────── #

def compute_verdict(metrics: dict[str, Any], *, split: str) -> dict[str, Any]:
    """Assign a deterministic verdict and explain exactly why.

    ``metrics`` is the output of :func:`metrics_view`. ``split`` is one of
    ``passed`` / ``failed`` / ``pending``.
    """

    pf = metrics.get("profit_factor")
    dd = metrics.get("drawdown_pct")
    trades = metrics.get("total_trades")
    net = metrics.get("net_profit")
    reasons: list[str] = []

    # INFRA ONLY — nothing was actually traded (smoke / zero-trade run).
    if trades is None or trades == 0:
        reasons.append("No trades were executed — this validates infrastructure, not a strategy.")
        return _verdict("INFRA_ONLY", "low", reasons)

    # REJECT — clearly not worth pursuing.
    if net is not None and net < 0:
        reasons.append(f"Net result is negative ({_fmt(net)}).")
        return _verdict("REJECT", "high", reasons)
    if split == "failed":
        reasons.append("Failed split validation — performance did not hold out of sample.")
        return _verdict("REJECT", "high", reasons)
    if dd is not None and dd >= 35:
        reasons.append(f"Max drawdown {_fmt(dd)}% is extreme.")
        return _verdict("REJECT", "high", reasons)
    if trades < 30:
        reasons.append(f"Only {trades} trades — far too few to trust.")
        return _verdict("REJECT", "medium", reasons)

    concentration = trades < 50 or (pf is not None and pf > 3.0)

    # GOOD — robust by our deterministic bar (requires split validation).
    if (
        pf is not None and pf >= 1.35
        and dd is not None and dd <= 20
        and trades >= 250
        and split == "passed"
        and not concentration
    ):
        reasons.append(f"Profit factor {_fmt(pf)} ≥ 1.35.")
        reasons.append(f"Drawdown {_fmt(dd)}% ≤ 20%.")
        reasons.append(f"{trades} trades is a solid sample.")
        reasons.append("Split validation passed.")
        return _verdict("GOOD", "high", reasons)

    # PROMISING — strong numbers but not yet proven robust.
    if (
        pf is not None and pf >= 1.20
        and dd is not None and dd <= 25
        and trades >= 100
    ):
        reasons.append(f"Profit factor {_fmt(pf)} ≥ 1.20.")
        reasons.append(f"Drawdown {_fmt(dd)}% ≤ 25%.")
        if split != "passed":
            reasons.append("Not yet split-validated — run validation before trusting it.")
        if concentration:
            reasons.append("Watch for concentration: few trades or an unusually high profit factor.")
        return _verdict("PROMISING", "medium", reasons)

    # WEAK — positive but unconvincing.
    if pf is not None and pf < 1.20:
        reasons.append(f"Profit factor {_fmt(pf)} is thin.")
    if trades < 100:
        reasons.append(f"Only {trades} trades — limited statistical confidence.")
    if dd is not None and dd > 25:
        reasons.append(f"Drawdown {_fmt(dd)}% is high relative to the edge.")
    if not reasons:
        reasons.append("Positive but below the promising bar.")
    return _verdict("WEAK", "low", reasons)


def _verdict(code: str, confidence: str, reasons: list[str]) -> dict[str, Any]:
    return {"code": code, "label": VERDICT_LABELS[code], "confidence": confidence, "reasons": reasons}


def _fmt(value: float | None) -> str:
    if value is None:
        return "—"
    if abs(value) >= 100:
        return f"{value:,.0f}"
    return f"{value:.2f}".rstrip("0").rstrip(".")


# ── Single-report analysis ───────────────────────────────────────────────── #

def build_run_analysis(row: dict[str, Any]) -> dict[str, Any]:
    metrics = metrics_view(row)
    split = split_status(row)
    verdict = compute_verdict(metrics, split=split)
    payload = row.get("parsed_metrics_payload") or {}
    parser_warnings = payload.get("parser_warnings", []) if isinstance(payload, dict) else []

    strengths: list[str] = []
    weaknesses: list[str] = []
    risk_notes: list[str] = []
    overfit: list[str] = []
    data_quality: list[str] = []

    pf, dd, trades = metrics["profit_factor"], metrics["drawdown_pct"], metrics["total_trades"]
    if pf is not None and pf >= 1.3:
        strengths.append(f"Profit factor {_fmt(pf)} indicates a real edge.")
    if dd is not None and dd <= 20:
        strengths.append(f"Drawdown {_fmt(dd)}% is well controlled.")
    if trades is not None and trades >= 250:
        strengths.append(f"{trades} trades give a reasonable statistical sample.")
    if metrics["recovery_factor"] is not None and metrics["recovery_factor"] >= 2:
        strengths.append(f"Recovery factor {_fmt(metrics['recovery_factor'])} is healthy.")

    if pf is not None and pf < 1.2:
        weaknesses.append(f"Profit factor {_fmt(pf)} is thin — small cost changes could erase it.")
    if trades is not None and trades < 100:
        weaknesses.append(f"Only {trades} trades — limited confidence in the result.")
    if dd is not None and dd > 25:
        risk_notes.append(f"Max drawdown {_fmt(dd)}% would be hard to sit through live.")
    if split != "passed":
        risk_notes.append("Not split-validated yet — the edge is unproven out of sample.")

    if pf is not None and pf > 3.0:
        overfit.append(f"Profit factor {_fmt(pf)} is unusually high — check for curve fitting.")
    if trades is not None and trades < 50 and (metrics["net_profit"] or 0) > 0:
        overfit.append("Few trades carry the whole result — likely sensitive to a handful of bars.")

    for warning in parser_warnings:
        if isinstance(warning, str) and warning.startswith("Metric not found"):
            data_quality.append(warning)
    if len(data_quality) > 4:
        data_quality = data_quality[:4] + [f"… and {len(data_quality) - 4} more missing metrics."]

    long_short = _long_short(metrics)

    return {
        "verdict": verdict,
        "metrics": metrics,
        "split_status": split,
        "strengths": strengths,
        "weaknesses": weaknesses,
        "risk_notes": risk_notes,
        "overfit_warnings": overfit,
        "data_quality_warnings": data_quality,
        "recommended_next_test": _recommend_next(verdict, metrics, split, long_short),
        "long_short": long_short,
        "data_available": dict(DATA_CAPABILITIES),
        "trade_level_note": TRADE_LEVEL_UNAVAILABLE_NOTE,
    }


def _long_short(metrics: dict[str, Any]) -> dict[str, Any]:
    longs, shorts = metrics.get("long_trades"), metrics.get("short_trades")
    available = longs is not None or shorts is not None
    total = (longs or 0) + (shorts or 0)
    return {
        "available": available,
        "pnl_available": False,  # per-side P&L needs trade-level deals
        "long_trades": longs,
        "short_trades": shorts,
        "long_share_pct": _round((longs or 0) / total * 100) if total else None,
        "short_share_pct": _round((shorts or 0) / total * 100) if total else None,
    }


def _recommend_next(
    verdict: dict[str, Any], metrics: dict[str, Any], split: str, long_short: dict[str, Any]
) -> str:
    code = verdict["code"]
    if code == "INFRA_ONLY":
        return "Infrastructure works. Run a real research test with a meaningful period and trade count."
    if code == "REJECT":
        return "Drop this configuration. Change the core idea or parameters before retesting."
    # Long/short imbalance hint (counts only — honest about the limit).
    longs, shorts = long_short.get("long_trades"), long_short.get("short_trades")
    if longs is not None and shorts is not None and (longs == 0) != (shorts == 0):
        side = "long-only" if shorts == 0 else "short-only"
        return f"Trades are entirely one-sided. Run a {side} vs the other-side ablation to confirm the edge."
    if split != "passed":
        return "Run split validation (in/out-of-sample) before trusting this candidate."
    if code == "PROMISING":
        return "Sweep nearby parameter values to check robustness, then re-run split validation."
    if code == "WEAK":
        return "Tighten filters or adjust risk/target, then retest — the current edge is too thin."
    return "Promote to champion and keep a challenger searching for improvements."


# ── Strategy board ───────────────────────────────────────────────────────── #

def candidate_score(metrics: dict[str, Any], split: str) -> float:
    pf = metrics.get("profit_factor") or 0.0
    dd = metrics.get("drawdown_pct")
    trades = metrics.get("total_trades") or 0
    return_pct = metrics.get("return_pct") or 0.0
    score = min(pf, 3.0) * 20.0
    score += min(max(return_pct, 0.0), 200.0) / 200.0 * 20.0
    score += min(trades, 500) / 500.0 * 15.0
    if dd is not None:
        score -= min(dd, 50.0)
    if split == "passed":
        score += 15.0
    return round(score, 1)


def _candidate_card(row: dict[str, Any]) -> dict[str, Any]:
    metrics = metrics_view(row)
    split = split_status(row)
    verdict = compute_verdict(metrics, split=split)
    return {
        "test_id": row.get("test_id"),
        "ea": row.get("ea", ""),
        "symbol": row.get("symbol", ""),
        "timeframe": row.get("timeframe", ""),
        "run_kind": row.get("run_kind", ""),
        "score": candidate_score(metrics, split),
        "verdict": verdict,
        "profit_factor": metrics.get("profit_factor"),
        "drawdown_pct": metrics.get("drawdown_pct"),
        "total_trades": metrics.get("total_trades"),
        "return_pct": metrics.get("return_pct"),
        "validation_status": split,
        "passed": bool(row.get("effective_pass_fail", row.get("pass_fail"))),
        "reason": row.get("effective_decision_reason") or row.get("effective_rejection_reason") or "",
        "created_at": row.get("created_at", ""),
    }


def build_strategy_board() -> dict[str, Any]:
    cards = [_candidate_card(row) for row in fetch_runs()]
    # Infra-only runs are not strategy candidates; keep them off the board.
    cards = [c for c in cards if c["verdict"]["code"] != "INFRA_ONLY"]
    cards.sort(key=lambda c: c["score"], reverse=True)

    good = [c for c in cards if c["verdict"]["code"] == "GOOD"]
    champion = good[0] if good else None
    champion_id = champion["test_id"] if champion else None

    challengers = [c for c in cards if c["verdict"]["code"] == "PROMISING"]
    rejected = [c for c in cards if c["verdict"]["code"] == "REJECT" or not c["passed"]]
    rejected_ids = {c["test_id"] for c in rejected}
    survivors = [
        c
        for c in cards
        if c["passed"]
        and c["test_id"] != champion_id
        and c["verdict"]["code"] != "PROMISING"
        and c["test_id"] not in rejected_ids
    ]

    return {
        "ok": True,
        "champion": champion,
        "challengers": challengers,
        "survivors": survivors,
        "rejected": rejected,
        "counts": {
            "champion": 1 if champion else 0,
            "challengers": len(challengers),
            "survivors": len(survivors),
            "rejected": len(rejected),
        },
    }


def latest_run_analysis() -> dict[str, Any]:
    row = fetch_latest_run()
    if row is None:
        return {"ok": True, "has_run": False}
    analysis = build_run_analysis(row)
    return {
        "ok": True,
        "has_run": True,
        "test_id": row.get("test_id"),
        "ea": row.get("ea", ""),
        "symbol": row.get("symbol", ""),
        "timeframe": row.get("timeframe", ""),
        "period": row.get("date_range", ""),
        "model": row.get("model", ""),
        "run_status": row.get("effective_run_status", row.get("run_status", "")),
        "created_at": row.get("created_at", ""),
        "decision_reason": row.get("effective_decision_reason") or row.get("decision_reason", ""),
        **analysis,
    }


def report_analysis(test_id: str) -> dict[str, Any]:
    row = fetch_run(test_id)
    if row is None:
        return {"ok": False, "error": "TEST_ID_NOT_FOUND", "test_id": test_id}
    analysis = build_run_analysis(row)
    return {
        "ok": True,
        "test_id": test_id,
        "ea": row.get("ea", ""),
        "symbol": row.get("symbol", ""),
        "timeframe": row.get("timeframe", ""),
        "period": row.get("date_range", ""),
        "model": row.get("model", ""),
        "deposit": row.get("deposit"),
        "run_status": row.get("effective_run_status", row.get("run_status", "")),
        "decision_reason": row.get("effective_decision_reason") or row.get("decision_reason", ""),
        "per_rule_results": row.get("effective_per_rule_results", row.get("per_rule_results", [])),
        "created_at": row.get("created_at", ""),
        **analysis,
    }
