from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any


DATE_PATTERN = re.compile(r"^\d{4}\.\d{2}\.\d{2}$")


@dataclass(slots=True)
class AcceptanceCriteria:
    min_profit: float
    min_profit_factor: float
    max_equity_dd_pct: float
    min_trades: int


@dataclass(slots=True)
class ResearchTask:
    test_id: str | None
    name: str
    ea: str
    symbol: str
    timeframe: str
    period_from: str
    period_to: str
    deposit: float
    model: str
    inputs: dict[str, str]
    acceptance: AcceptanceCriteria


def _require_non_empty_string(data: dict[str, Any], field_name: str) -> str:
    value = data.get(field_name)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"Field '{field_name}' must be a non-empty string.")
    return value.strip()


def _require_date_string(data: dict[str, Any], field_name: str) -> str:
    value = _require_non_empty_string(data, field_name)
    if not DATE_PATTERN.match(value):
        raise ValueError(f"Field '{field_name}' must use YYYY.MM.DD format.")
    return value


def _require_number(data: dict[str, Any], field_name: str) -> float:
    value = data.get(field_name)
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        raise ValueError(f"Field '{field_name}' must be numeric.")
    return float(value)


def _require_int(data: dict[str, Any], field_name: str) -> int:
    value = data.get(field_name)
    if not isinstance(value, int) or isinstance(value, bool):
        raise ValueError(f"Field '{field_name}' must be an integer.")
    return value


def _validate_inputs(data: dict[str, Any]) -> dict[str, str]:
    value = data.get("inputs")
    if not isinstance(value, dict):
        raise ValueError("Field 'inputs' must be an object.")

    normalized: dict[str, str] = {}
    for key, item in value.items():
        if not isinstance(key, str) or not key.strip():
            raise ValueError("Every input key must be a non-empty string.")
        if not isinstance(item, str) or not item.strip():
            raise ValueError(f"Input '{key}' must have a non-empty string value.")
        normalized[key.strip()] = item.strip()
    return normalized


def _validate_acceptance(data: dict[str, Any]) -> AcceptanceCriteria:
    value = data.get("acceptance")
    if not isinstance(value, dict):
        raise ValueError("Field 'acceptance' must be an object.")

    return AcceptanceCriteria(
        min_profit=_require_number(value, "min_profit"),
        min_profit_factor=_require_number(value, "min_profit_factor"),
        max_equity_dd_pct=_require_number(value, "max_equity_dd_pct"),
        min_trades=_require_int(value, "min_trades"),
    )


def validate_task_payload(payload: dict[str, Any]) -> ResearchTask:
    test_id = payload.get("test_id")
    if test_id is not None:
        if not isinstance(test_id, str) or not test_id.strip():
            raise ValueError("Field 'test_id' must be a non-empty string when provided.")
        test_id = test_id.strip()
    task = ResearchTask(
        test_id=test_id,
        name=_require_non_empty_string(payload, "name"),
        ea=_require_non_empty_string(payload, "ea"),
        symbol=_require_non_empty_string(payload, "symbol"),
        timeframe=_require_non_empty_string(payload, "timeframe"),
        period_from=_require_date_string(payload, "period_from"),
        period_to=_require_date_string(payload, "period_to"),
        deposit=_require_number(payload, "deposit"),
        model=_require_non_empty_string(payload, "model"),
        inputs=_validate_inputs(payload),
        acceptance=_validate_acceptance(payload),
    )
    return task


def load_task(task_path: str | Path) -> ResearchTask:
    path = Path(task_path)
    with path.open("r", encoding="utf-8") as handle:
        payload = json.load(handle)
    if not isinstance(payload, dict):
        raise ValueError("Task file must contain a JSON object.")
    return validate_task_payload(payload)


def task_to_payload(task: ResearchTask) -> dict[str, Any]:
    return asdict(task)
