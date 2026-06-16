from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from mt5_research_agent.config import load_config
from mt5_research_agent.report_parser import metrics_drawdown_pct, normalize_line
from mt5_research_agent.result_store import fetch_runs, get_db_path, get_results_dir, update_leaderboard_csv, update_summary_md
from mt5_research_agent.run_task import execute_run_task
from mt5_research_agent.task import ResearchTask, load_task, task_to_payload


@dataclass(slots=True)
class SplitWindow:
    label: str
    period_from: str
    period_to: str


@dataclass(slots=True)
class SplitAcceptance:
    all_splits_profitable: bool
    min_profit_factor_each_split: float
    max_equity_dd_pct_each_split: float
    min_trades_each_split: int


@dataclass(slots=True)
class SplitExperiment:
    name: str
    base_task: str
    splits: list[SplitWindow]
    acceptance: SplitAcceptance


def _require_non_empty_string(data: dict[str, Any], field_name: str) -> str:
    value = data.get(field_name)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"Field '{field_name}' must be a non-empty string.")
    return value.strip()


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


def _validate_splits(data: dict[str, Any]) -> list[SplitWindow]:
    value = data.get("splits")
    if not isinstance(value, list) or not value:
        raise ValueError("Field 'splits' must be a non-empty array.")
    splits: list[SplitWindow] = []
    for item in value:
        if not isinstance(item, dict):
            raise ValueError("Each split must be an object.")
        splits.append(
            SplitWindow(
                label=_require_non_empty_string(item, "label"),
                period_from=_require_non_empty_string(item, "from"),
                period_to=_require_non_empty_string(item, "to"),
            )
        )
    return splits


def _validate_acceptance(data: dict[str, Any]) -> SplitAcceptance:
    value = data.get("acceptance")
    if not isinstance(value, dict):
        raise ValueError("Field 'acceptance' must be an object.")
    profitable = value.get("all_splits_profitable")
    if not isinstance(profitable, bool):
        raise ValueError("Field 'acceptance.all_splits_profitable' must be a boolean.")
    return SplitAcceptance(
        all_splits_profitable=profitable,
        min_profit_factor_each_split=_require_number(value, "min_profit_factor_each_split"),
        max_equity_dd_pct_each_split=_require_number(value, "max_equity_dd_pct_each_split"),
        min_trades_each_split=_require_int(value, "min_trades_each_split"),
    )


def validate_split_experiment_payload(payload: dict[str, Any]) -> SplitExperiment:
    return SplitExperiment(
        name=_require_non_empty_string(payload, "name"),
        base_task=_require_non_empty_string(payload, "base_task"),
        splits=_validate_splits(payload),
        acceptance=_validate_acceptance(payload),
    )


def load_split_experiment(experiment_path: str | Path) -> SplitExperiment:
    path = Path(experiment_path)
    with path.open("r", encoding="utf-8") as handle:
        payload = json.load(handle)
    if not isinstance(payload, dict):
        raise ValueError("Split experiment file must contain a JSON object.")
    return validate_split_experiment_payload(payload)


def candidate_prefix(name: str) -> str:
    token = normalize_line(name).split("_", 1)[0]
    token = "".join(char for char in token if char.isalnum()).upper()
    return token or "CAND"


def _existing_candidate_ids(prefix: str) -> list[int]:
    rows = fetch_runs()
    ids: list[int] = []
    for row in rows:
        candidate_id = row.get("parent_candidate_id") or row.get("test_id") or ""
        if not candidate_id.startswith(f"{prefix}-"):
            continue
        try:
            ids.append(int(candidate_id.split("-", 1)[1]))
        except (IndexError, ValueError):
            continue
    return ids


def next_candidate_id(name: str) -> str:
    prefix = candidate_prefix(name)
    current = _existing_candidate_ids(prefix)
    next_index = max(current, default=0) + 1
    return f"{prefix}-{next_index:04d}"


def build_split_tasks(experiment: SplitExperiment, base_task: ResearchTask, candidate_id: str) -> list[dict[str, Any]]:
    tasks: list[dict[str, Any]] = []
    for index, split in enumerate(experiment.splits, start=1):
        task_payload = task_to_payload(base_task)
        task_payload["name"] = f"{experiment.name}_{candidate_id.lower()}_{split.label.lower()}"
        task_payload["test_id"] = f"{candidate_id}-S{index:02d}"
        task_payload["period_from"] = split.period_from
        task_payload["period_to"] = split.period_to
        tasks.append(task_payload)
    return tasks


def split_tasks_dir(experiment_name: str, candidate_id: str) -> Path:
    config = load_config()
    path = Path(config.artifacts_dir).resolve() / "generated_tasks" / experiment_name / candidate_id
    path.mkdir(parents=True, exist_ok=True)
    return path


def write_split_tasks(experiment: SplitExperiment, candidate_id: str, tasks: list[dict[str, Any]]) -> list[Path]:
    output_dir = split_tasks_dir(experiment.name, candidate_id)
    paths: list[Path] = []
    for task_payload in tasks:
        path = output_dir / f"{task_payload['test_id']}.json"
        path.write_text(json.dumps(task_payload, indent=2), encoding="utf-8")
        paths.append(path)
    return paths


def evaluate_split_row(row: dict[str, Any], acceptance: SplitAcceptance) -> tuple[bool, list[str]]:
    metrics = json.loads(row["parsed_metrics_json"])
    reasons: list[str] = []

    net_profit = metrics.get("net_profit")
    if acceptance.all_splits_profitable and (net_profit is None or net_profit <= 0):
        reasons.append("SPLIT_NOT_PROFITABLE")

    profit_factor = metrics.get("profit_factor")
    if profit_factor is None or profit_factor < acceptance.min_profit_factor_each_split:
        reasons.append("SPLIT_MIN_PROFIT_FACTOR")

    drawdown = metrics_drawdown_pct(metrics)
    if drawdown is None or drawdown > acceptance.max_equity_dd_pct_each_split:
        reasons.append("SPLIT_MAX_EQUITY_DD_PCT")

    total_trades = metrics.get("total_trades")
    if total_trades is None or total_trades < acceptance.min_trades_each_split:
        reasons.append("SPLIT_MIN_TRADES")

    return (not reasons, reasons)


def evaluate_split_report(parsed_report, acceptance: SplitAcceptance) -> tuple[bool, str]:
    row = {
        "parsed_metrics_json": json.dumps(
            {
                "net_profit": parsed_report.net_profit,
                "profit_factor": parsed_report.profit_factor,
                "equity_drawdown_pct": parsed_report.equity_drawdown_pct,
                "relative_drawdown_pct": parsed_report.relative_drawdown_pct,
                "total_trades": parsed_report.total_trades,
            }
        )
    }
    passed, reasons = evaluate_split_row(row, acceptance)
    return passed, ";".join(reasons)


def split_validation_report_path(experiment_name: str) -> Path:
    return get_results_dir() / f"split_validation_{experiment_name}.md"


def write_split_validation_report(
    experiment: SplitExperiment,
    candidate_id: str,
    rows: list[dict[str, Any]],
    final_passed: bool,
) -> Path:
    output_path = split_validation_report_path(experiment.name)
    lines = [
        f"# Split Validation {experiment.name}",
        "",
        f"- Candidate ID: {candidate_id}",
        f"- Decision: {'PASS' if final_passed else 'FAIL'}",
        "",
        "| Test ID | Split | Date Range | Pass/Fail | Net Profit | PF | DD % | Trades | Reason |",
        "| --- | --- | --- | --- | --- | --- | --- | --- | --- |",
    ]
    for row in rows:
        metrics = json.loads(row["parsed_metrics_json"])
        lines.append(
            f"| {row['test_id']} | {row['split_id'] or '-'} | {row['date_range']} | {'PASS' if row['pass_fail'] else 'FAIL'} | "
            f"{metrics.get('net_profit')} | {metrics.get('profit_factor')} | {metrics_drawdown_pct(metrics)} | "
            f"{metrics.get('total_trades')} | {row['rejection_reason'] or '-'} |"
        )
    output_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return output_path


def fetch_candidate_rows(candidate_id: str) -> list[dict[str, Any]]:
    rows = fetch_runs()
    return [row for row in rows if row.get("parent_candidate_id") == candidate_id or row.get("test_id") == candidate_id]


def update_candidate_split_result(test_id: str, passed: bool, rejection_reason: str) -> None:
    db_path = get_db_path()
    with sqlite3.connect(db_path) as connection:
        connection.execute(
            "UPDATE runs SET pass_fail = ?, rejection_reason = ? WHERE test_id = ?",
            (1 if passed else 0, rejection_reason, test_id),
        )


def summarize_candidate(candidate_id: str) -> Path:
    rows = fetch_candidate_rows(candidate_id)
    output_path = get_results_dir() / f"candidate_{candidate_id}.md"
    lines = [f"# Candidate {candidate_id}", ""]
    if not rows:
        lines.append("No stored runs found for this candidate.")
    else:
        lines.append("| Test ID | Kind | Split | Date Range | Pass/Fail | PF | Net Profit | DD % | Trades | Reason |")
        lines.append("| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |")
        for row in rows:
            metrics = json.loads(row["parsed_metrics_json"])
            lines.append(
                f"| {row['test_id']} | {row['run_kind']} | {row['split_id'] or '-'} | {row['date_range']} | "
                f"{'PASS' if row['pass_fail'] else 'FAIL'} | {metrics.get('profit_factor')} | {metrics.get('net_profit')} | "
                f"{metrics_drawdown_pct(metrics)} | {metrics.get('total_trades')} | {row['rejection_reason'] or '-'} |"
            )
    output_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return output_path


def run_run_splits_command(experiment_path: str, allow_gui_clicks: bool, timeout_seconds: int = 1800) -> int:
    if not allow_gui_clicks:
        print("Refusing to run split validation without --allow-gui-clicks.")
        return 2

    try:
        experiment = load_split_experiment(experiment_path)
        base_task = load_task(experiment.base_task)
        candidate_id = next_candidate_id(experiment.name)
        tasks = build_split_tasks(experiment, base_task, candidate_id)
        task_paths = write_split_tasks(experiment, candidate_id, tasks)

        for index, task_path in enumerate(task_paths, start=1):
            result = execute_run_task(
                str(task_path),
                allow_gui_clicks=True,
                timeout_seconds=timeout_seconds,
                execution_mode="cli",
                run_kind="split",
                parent_candidate_id=candidate_id,
                split_id=experiment.splits[index - 1].label,
                acceptance_evaluator=lambda parsed_report, _: evaluate_split_report(parsed_report, experiment.acceptance),
            )
            if result.safety_ui_failure:
                print(f"split validation stopped on safety/UI failure at {tasks[index - 1]['test_id']}")
                print(f"log: {result.log_path}")
                return 1

        rows = [row for row in fetch_runs() if row.get("parent_candidate_id") == candidate_id and row.get("run_kind") == "split"]
        for row in rows:
            if row["rejection_reason"] == "REPORT_MISSING":
                continue
            if row["parsed_metrics_json"]:
                passed, reasons = evaluate_split_row(row, experiment.acceptance)
                update_candidate_split_result(row["test_id"], passed, ";".join(reasons))
        rows = [row for row in fetch_runs() if row.get("parent_candidate_id") == candidate_id and row.get("run_kind") == "split"]
        final_passed = bool(rows) and all(row["pass_fail"] for row in rows)
        report_path = write_split_validation_report(experiment, candidate_id, rows, final_passed)
        update_leaderboard_csv()
        update_summary_md()
        print(f"candidate_id: {candidate_id}")
        print(f"decision: {'PASS' if final_passed else 'FAIL'}")
        print(f"report: {report_path}")
        return 0 if final_passed else 1
    except Exception as exc:
        print(str(exc))
        return 1
