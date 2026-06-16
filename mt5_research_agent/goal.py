"""Structured goal support for goal-seeking research.

A goal describes the *target* the research loop tries to reach (for example
"+250% over 5 years with drawdown under 25%") plus the search budget. It is
deliberately separate from per-test acceptance ("hard limits"): acceptance
decides whether a single backtest passes, while the goal decides when the whole
search should stop and which candidate is "best robust" versus "closest raw".

Safety: a goal can never request live trading and is never satisfied by a single
lucky full-period run. The goal-seeking loop additionally requires split
validation when ``must_validate_splits`` is true.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any


DEFAULT_OBJECTIVE = "maximize robust return under drawdown and validation constraints"


@dataclass(slots=True)
class ResearchGoal:
    target_total_return_pct: float | None = None
    target_period_years: float | None = None
    max_equity_drawdown_pct: float | None = None
    min_profit_factor: float | None = None
    min_trades: int | None = None
    must_validate_splits: bool = True
    max_tests: int = 50
    max_runtime_minutes: int | None = None
    objective: str = DEFAULT_OBJECTIVE


def _coerce_float(value: Any, field_name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float, str)):
        raise ValueError(f"Field '{field_name}' must be numeric.")
    try:
        return float(value)
    except (TypeError, ValueError):
        raise ValueError(f"Field '{field_name}' must be numeric.") from None


def _coerce_int(value: Any, field_name: str) -> int:
    if isinstance(value, bool):
        raise ValueError(f"Field '{field_name}' must be an integer.")
    if isinstance(value, int):
        return value
    try:
        return int(str(value).strip())
    except (TypeError, ValueError):
        raise ValueError(f"Field '{field_name}' must be an integer.") from None


def _coerce_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    return str(value).strip().casefold() in {"true", "1", "yes", "y"}


def validate_goal_payload(payload: dict[str, Any]) -> ResearchGoal:
    if not isinstance(payload, dict):
        raise ValueError("Goal must be a JSON object.")

    goal = ResearchGoal()
    if "target_total_return_pct" in payload and payload["target_total_return_pct"] is not None:
        goal.target_total_return_pct = _coerce_float(payload["target_total_return_pct"], "target_total_return_pct")
    if "target_period_years" in payload and payload["target_period_years"] is not None:
        goal.target_period_years = _coerce_float(payload["target_period_years"], "target_period_years")
    if "max_equity_drawdown_pct" in payload and payload["max_equity_drawdown_pct"] is not None:
        goal.max_equity_drawdown_pct = _coerce_float(payload["max_equity_drawdown_pct"], "max_equity_drawdown_pct")
    if "min_profit_factor" in payload and payload["min_profit_factor"] is not None:
        goal.min_profit_factor = _coerce_float(payload["min_profit_factor"], "min_profit_factor")
    if "min_trades" in payload and payload["min_trades"] is not None:
        goal.min_trades = _coerce_int(payload["min_trades"], "min_trades")
    if "must_validate_splits" in payload:
        goal.must_validate_splits = _coerce_bool(payload["must_validate_splits"])
    if "max_tests" in payload and payload["max_tests"] is not None:
        max_tests = _coerce_int(payload["max_tests"], "max_tests")
        if max_tests <= 0:
            raise ValueError("Field 'max_tests' must be a positive integer.")
        goal.max_tests = max_tests
    if "max_runtime_minutes" in payload and payload["max_runtime_minutes"] is not None:
        goal.max_runtime_minutes = _coerce_int(payload["max_runtime_minutes"], "max_runtime_minutes")
    if payload.get("objective"):
        goal.objective = str(payload["objective"]).strip()
    return goal


def parse_goal_section(items: dict[str, str]) -> ResearchGoal | None:
    """Build a goal from key/value bullet items in a `## Goal constraints` block.

    Returns ``None`` when no recognized goal keys are present so callers can
    treat the goal as optional.
    """

    recognized = {
        "target_total_return_pct",
        "target_period_years",
        "max_equity_drawdown_pct",
        "min_profit_factor",
        "min_trades",
        "must_validate_splits",
        "max_tests",
        "max_runtime_minutes",
        "objective",
    }
    payload = {key: value for key, value in items.items() if key in recognized}
    if not payload:
        return None
    return validate_goal_payload(payload)


def goal_to_payload(goal: ResearchGoal) -> dict[str, Any]:
    return asdict(goal)


def load_goal(goal_path: str | Path) -> ResearchGoal:
    path = Path(goal_path)
    payload = json.loads(path.read_text(encoding="utf-8"))
    return validate_goal_payload(payload)


def describe_goal(goal: ResearchGoal) -> list[str]:
    return [
        f"objective: {goal.objective}",
        f"target_total_return_pct: {goal.target_total_return_pct}",
        f"target_period_years: {goal.target_period_years}",
        f"max_equity_drawdown_pct: {goal.max_equity_drawdown_pct}",
        f"min_profit_factor: {goal.min_profit_factor}",
        f"min_trades: {goal.min_trades}",
        f"must_validate_splits: {goal.must_validate_splits}",
        f"max_tests: {goal.max_tests}",
        f"max_runtime_minutes: {goal.max_runtime_minutes}",
    ]
