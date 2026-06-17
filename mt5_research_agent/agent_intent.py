"""Natural-language goal parsing for the desktop Agent tab.

The desktop app lets a user type a free-form research goal such as::

    Test XAUUSD H1 until PF is near 1.5, max DD 20%, minimum 300 trades,
    split validation required

:func:`parse_agent_prompt` turns that into a structured, *editable* plan the UI
can render as goal chips (symbol, timeframe, target profit factor, ...). It is a
pure, dependency-free function so it is trivially unit-testable and never raises
on odd input — unknown fields simply stay ``None``.
"""

from __future__ import annotations

import re
from typing import Any


# Modes the Agent tab exposes. The UI mirrors these labels.
MODES = {
    "research_existing": "Research existing EA",
    "create_new": "Create new EA",
    "optimize": "Optimize parameters",
    "diagnose": "Diagnose failed run",
    "report": "Generate report",
}

_TIMEFRAMES = ("M1", "M5", "M15", "M30", "H1", "H4", "D1", "W1", "MN1", "MN")

# A small set of well-known instruments plus a generic 6-letter FX pattern.
_KNOWN_SYMBOLS = (
    "XAUUSD", "XAGUSD", "BTCUSD", "ETHUSD", "US30", "US500", "US100", "USTEC",
    "NAS100", "SPX500", "GER40", "GER30", "UK100", "JP225", "AUS200",
    "USOIL", "WTI",
)


def _first_float(pattern: str, text: str) -> float | None:
    match = re.search(pattern, text, re.IGNORECASE)
    if not match:
        return None
    try:
        return float(match.group(1))
    except (TypeError, ValueError):
        return None


def _first_int(pattern: str, text: str) -> int | None:
    value = _first_float(pattern, text)
    return int(value) if value is not None else None


def _detect_symbol(text: str) -> str | None:
    upper = text.upper()
    for symbol in _KNOWN_SYMBOLS:
        if symbol in upper:
            return symbol
    # Generic 6-letter FX pair, e.g. EURUSD, GBPJPY.
    match = re.search(r"\b([A-Z]{3}(?:USD|EUR|JPY|GBP|CHF|AUD|CAD|NZD))\b", upper)
    return match.group(1) if match else None


def _detect_timeframe(text: str) -> str | None:
    upper = text.upper()
    for tf in _TIMEFRAMES:
        if re.search(rf"\b{tf}\b", upper):
            return "MN1" if tf == "MN" else tf
    return None


def _detect_mode(text: str, requested: str | None) -> str:
    if requested in MODES:
        return requested
    lowered = text.lower()
    if any(
        w in lowered
        for w in ("create", "new ea", "generate an ea", "build an ea", "build a ", "build me", "scaffold")
    ):
        return "create_new"
    if any(w in lowered for w in ("diagnose", "why did", "failed run", "failing", "debug")):
        return "diagnose"
    if any(w in lowered for w in ("optimize", "optimise", "tune", "grid", "parameter sweep")):
        return "optimize"
    if "report" in lowered and "reporting" not in lowered:
        return "report"
    return "research_existing"


def parse_agent_prompt(prompt: str, mode: str | None = None) -> dict[str, Any]:
    """Parse a free-form research goal into a structured, editable plan."""

    text = (prompt or "").strip()
    resolved_mode = _detect_mode(text, mode)

    split_validation = bool(
        re.search(r"split[\s-]?valid|walk[\s-]?forward|out[\s-]?of[\s-]?sample", text, re.IGNORECASE)
    )

    goals: dict[str, Any] = {
        "symbol": _detect_symbol(text),
        "timeframe": _detect_timeframe(text),
        "target_profit_factor": _first_float(
            r"(?:profit\s*factor|\bpf\b)\D{0,14}(\d+(?:\.\d+)?)", text
        ),
        "target_return_pct": _first_float(r"(\d+(?:\.\d+)?)\s*%?\s*return|return\D{0,10}(\d+(?:\.\d+)?)\s*%", text),
        "max_drawdown_pct": _first_float(
            r"(?:max(?:imum)?\s*)?(?:draw[\s-]?down|\bdd\b)\D{0,10}(\d+(?:\.\d+)?)", text
        ),
        "min_trades": _first_int(r"(?:min(?:imum)?\s*)?(\d+)\s*\+?\s*trades|trades\D{0,10}(\d+)", text),
        "max_tests": _first_int(r"(?:max(?:imum)?\s*)?(\d+)\s*tests|tests\D{0,10}(\d+)", text),
        "max_runtime_minutes": _detect_runtime_minutes(text),
        "split_validation": split_validation,
    }

    return {
        "ok": True,
        "mode": resolved_mode,
        "mode_label": MODES[resolved_mode],
        "goals": goals,
        "chips": _build_chips(goals),
        "summary": _build_summary(resolved_mode, goals),
    }


def _detect_runtime_minutes(text: str) -> int | None:
    match = re.search(r"(\d+(?:\.\d+)?)\s*(hours?|hrs?|minutes?|mins?)\b", text, re.IGNORECASE)
    if not match:
        match = re.search(r"runtime\D{0,10}(\d+(?:\.\d+)?)\s*(hours?|hrs?|minutes?|mins?)?", text, re.IGNORECASE)
        if not match:
            return None
    value = float(match.group(1))
    unit = (match.group(2) or "minutes").lower()
    if unit.startswith(("h", "hr")):
        value *= 60
    return int(value)


_CHIP_LABELS = {
    "symbol": "Symbol",
    "timeframe": "Timeframe",
    "target_profit_factor": "Target PF",
    "target_return_pct": "Target return %",
    "max_drawdown_pct": "Max DD %",
    "min_trades": "Min trades",
    "max_tests": "Max tests",
    "max_runtime_minutes": "Max runtime (min)",
    "split_validation": "Split validation",
}


def _build_chips(goals: dict[str, Any]) -> list[dict[str, Any]]:
    chips: list[dict[str, Any]] = []
    for key, label in _CHIP_LABELS.items():
        value = goals.get(key)
        if key == "split_validation":
            chips.append({"key": key, "label": label, "value": bool(value), "kind": "bool"})
        elif value is not None:
            kind = "text" if key in ("symbol", "timeframe") else "number"
            chips.append({"key": key, "label": label, "value": value, "kind": kind})
    return chips


def _build_summary(mode: str, goals: dict[str, Any]) -> str:
    parts: list[str] = [MODES[mode]]
    symbol = goals.get("symbol")
    timeframe = goals.get("timeframe")
    if symbol:
        parts.append(f"on {symbol}" + (f" {timeframe}" if timeframe else ""))
    elif timeframe:
        parts.append(f"on {timeframe}")
    targets: list[str] = []
    if goals.get("target_profit_factor") is not None:
        targets.append(f"PF ≈ {goals['target_profit_factor']}")
    if goals.get("target_return_pct") is not None:
        targets.append(f"return ≥ {goals['target_return_pct']}%")
    if goals.get("max_drawdown_pct") is not None:
        targets.append(f"max DD ≤ {goals['max_drawdown_pct']}%")
    if goals.get("min_trades") is not None:
        targets.append(f"≥ {goals['min_trades']} trades")
    if targets:
        parts.append("until " + ", ".join(targets))
    if goals.get("split_validation"):
        parts.append("with split validation")
    return " ".join(parts) + "."
