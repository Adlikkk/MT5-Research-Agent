import json

import pytest

from mt5_research_agent.goal import (
    load_goal,
    parse_goal_section,
    validate_goal_payload,
)


def test_validate_goal_payload_full_shape() -> None:
    goal = validate_goal_payload(
        {
            "target_total_return_pct": 250,
            "target_period_years": 5,
            "max_equity_drawdown_pct": 25,
            "min_profit_factor": 1.2,
            "min_trades": 250,
            "must_validate_splits": True,
            "max_tests": 200,
            "max_runtime_minutes": 360,
            "objective": "robust return",
        }
    )

    assert goal.target_total_return_pct == 250.0
    assert goal.min_trades == 250
    assert goal.must_validate_splits is True
    assert goal.max_tests == 200
    assert goal.objective == "robust return"


def test_validate_goal_payload_defaults() -> None:
    goal = validate_goal_payload({})
    assert goal.must_validate_splits is True
    assert goal.max_tests == 50
    assert goal.target_total_return_pct is None


def test_validate_goal_payload_rejects_bad_max_tests() -> None:
    with pytest.raises(ValueError):
        validate_goal_payload({"max_tests": 0})


def test_parse_goal_section_from_bullets() -> None:
    goal = parse_goal_section(
        {
            "target_total_return_pct": "250",
            "max_equity_drawdown_pct": "25",
            "must_validate_splits": "true",
            "max_tests": "120",
        }
    )
    assert goal is not None
    assert goal.target_total_return_pct == 250.0
    assert goal.max_equity_drawdown_pct == 25.0
    assert goal.max_tests == 120


def test_parse_goal_section_returns_none_when_empty() -> None:
    assert parse_goal_section({"unrelated": "x"}) is None


def test_load_goal_roundtrip(tmp_path) -> None:
    path = tmp_path / "goal.json"
    path.write_text(json.dumps({"target_total_return_pct": 100, "max_tests": 10}), encoding="utf-8")
    goal = load_goal(path)
    assert goal.target_total_return_pct == 100.0
    assert goal.max_tests == 10
