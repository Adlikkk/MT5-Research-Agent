from mt5_research_agent.agent_intent import parse_agent_prompt
from mt5_research_agent.api import handle_api_request


def test_parses_full_research_prompt() -> None:
    result = parse_agent_prompt(
        "Test XAUUSD H1 until PF is near 1.5, max DD 20%, "
        "minimum 300 trades, split validation required"
    )

    goals = result["goals"]
    assert result["ok"] is True
    assert result["mode"] == "research_existing"
    assert goals["symbol"] == "XAUUSD"
    assert goals["timeframe"] == "H1"
    assert goals["target_profit_factor"] == 1.5
    assert goals["max_drawdown_pct"] == 20.0
    assert goals["min_trades"] == 300
    assert goals["split_validation"] is True
    assert any(c["key"] == "symbol" for c in result["chips"])
    assert "XAUUSD" in result["summary"]


def test_detects_modes_from_keywords() -> None:
    assert parse_agent_prompt("Create a new EA for EURUSD")["mode"] == "create_new"
    assert parse_agent_prompt("Optimize the parameters on GBPUSD")["mode"] == "optimize"
    assert parse_agent_prompt("Diagnose why did this run fail")["mode"] == "diagnose"


def test_recognizes_index_symbols_and_build_intent() -> None:
    result = parse_agent_prompt("Build a US100 M15 strategy until PF near 1.4, DD under 18%")
    assert result["mode"] == "create_new"
    assert result["goals"]["symbol"] == "US100"
    assert result["goals"]["timeframe"] == "M15"


def test_explicit_mode_overrides_detection() -> None:
    result = parse_agent_prompt("look at EURUSD", mode="optimize")
    assert result["mode"] == "optimize"


def test_runtime_hours_converted_to_minutes() -> None:
    result = parse_agent_prompt("Research US30 M5 for 2 hours")
    assert result["goals"]["max_runtime_minutes"] == 120


def test_empty_prompt_is_safe() -> None:
    result = parse_agent_prompt("")
    assert result["ok"] is True
    assert result["goals"]["symbol"] is None


def test_agent_parse_endpoint() -> None:
    status, payload = handle_api_request(
        "POST", "/agent/parse", {"prompt": "Test EURUSD H4 PF 1.3 min 200 trades"}
    )
    assert status == 200
    assert payload["goals"]["symbol"] == "EURUSD"
    assert payload["goals"]["timeframe"] == "H4"


def test_agent_parse_requires_prompt() -> None:
    status, payload = handle_api_request("POST", "/agent/parse", {})
    assert status == 400
    assert payload["ok"] is False
