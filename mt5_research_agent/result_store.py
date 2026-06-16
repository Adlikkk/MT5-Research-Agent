from __future__ import annotations

import csv
import json
import sqlite3
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from mt5_research_agent.config import load_config
from mt5_research_agent.report_parser import (
    CORE_METRIC_FIELDS,
    ParsedReport,
    normalized_metrics_payload,
    parse_report_file,
    parsed_report_to_payload,
)
from mt5_research_agent.task import validate_task_payload


@dataclass(slots=True)
class StoredRun:
    test_id: str
    run_status: str
    execution_mode: str
    run_kind: str
    parent_candidate_id: str
    split_id: str
    task_name: str
    ea: str
    symbol: str
    timeframe: str
    date_range: str
    deposit: float
    model: str
    full_inputs_json: dict[str, Any]
    parsed_metrics_json: dict[str, Any]
    passed: bool
    rejection_reason: str
    decision_reason: str
    per_rule_results: list[dict[str, Any]]
    raw_report_path: str
    parsed_report_path: str
    screenshot_path: str
    created_at: str


@dataclass(slots=True)
class RunAttempt:
    attempt_id: str
    test_id: str
    run_status: str
    execution_mode: str
    run_kind: str
    parent_candidate_id: str
    split_id: str
    task_name: str
    raw_report_path: str
    parsed_report_path: str
    log_path: str
    set_path: str
    ini_path: str
    command_line: str
    expected_report_path: str
    discovered_report_path: str
    process_id: int | None
    process_exit_code: int | None
    process_started_at: str
    process_ended_at: str
    duration_seconds: float | None
    parsed_metrics_json: dict[str, Any] = field(default_factory=dict)
    decision_reason: str = ""
    per_rule_results: list[dict[str, Any]] = field(default_factory=list)
    error: str = ""
    created_at: str = ""


@dataclass(slots=True)
class AcceptanceEvaluation:
    passed: bool
    status: str
    rejection_reason: str
    decision_reason: str
    per_rule_results: list[dict[str, Any]] = field(default_factory=list)
    missing_metrics: list[str] = field(default_factory=list)
    metrics_used: dict[str, Any] = field(default_factory=dict)


def get_results_dir() -> Path:
    config = load_config()
    path = Path(config.results_dir).resolve()
    path.mkdir(parents=True, exist_ok=True)
    return path


def get_db_path() -> Path:
    return get_results_dir() / "runs.sqlite"


def get_leaderboard_path() -> Path:
    return get_results_dir() / "leaderboard.csv"


def get_summary_path() -> Path:
    return get_results_dir() / "summary.md"


def get_parsed_reports_dir() -> Path:
    config = load_config()
    path = Path(config.artifacts_dir).resolve() / "parsed_reports"
    path.mkdir(parents=True, exist_ok=True)
    return path


def _ensure_run_columns(connection: sqlite3.Connection) -> None:
    columns = {row[1] for row in connection.execute("PRAGMA table_info(runs)").fetchall()}
    if "run_status" not in columns:
        connection.execute("ALTER TABLE runs ADD COLUMN run_status TEXT NOT NULL DEFAULT ''")
    if "execution_mode" not in columns:
        connection.execute("ALTER TABLE runs ADD COLUMN execution_mode TEXT NOT NULL DEFAULT ''")
    if "run_kind" not in columns:
        connection.execute("ALTER TABLE runs ADD COLUMN run_kind TEXT NOT NULL DEFAULT 'full_period'")
    if "parent_candidate_id" not in columns:
        connection.execute("ALTER TABLE runs ADD COLUMN parent_candidate_id TEXT NOT NULL DEFAULT ''")
    if "split_id" not in columns:
        connection.execute("ALTER TABLE runs ADD COLUMN split_id TEXT NOT NULL DEFAULT ''")
    if "parsed_report_path" not in columns:
        connection.execute("ALTER TABLE runs ADD COLUMN parsed_report_path TEXT NOT NULL DEFAULT ''")
    if "decision_reason" not in columns:
        connection.execute("ALTER TABLE runs ADD COLUMN decision_reason TEXT NOT NULL DEFAULT ''")
    if "per_rule_results_json" not in columns:
        connection.execute("ALTER TABLE runs ADD COLUMN per_rule_results_json TEXT NOT NULL DEFAULT '[]'")


def _ensure_attempt_columns(connection: sqlite3.Connection) -> None:
    columns = {row[1] for row in connection.execute("PRAGMA table_info(run_attempts)").fetchall()}
    if "command_line" not in columns:
        connection.execute("ALTER TABLE run_attempts ADD COLUMN command_line TEXT NOT NULL DEFAULT ''")
    if "expected_report_path" not in columns:
        connection.execute("ALTER TABLE run_attempts ADD COLUMN expected_report_path TEXT NOT NULL DEFAULT ''")
    if "discovered_report_path" not in columns:
        connection.execute("ALTER TABLE run_attempts ADD COLUMN discovered_report_path TEXT NOT NULL DEFAULT ''")
    if "process_started_at" not in columns:
        connection.execute("ALTER TABLE run_attempts ADD COLUMN process_started_at TEXT NOT NULL DEFAULT ''")
    if "process_ended_at" not in columns:
        connection.execute("ALTER TABLE run_attempts ADD COLUMN process_ended_at TEXT NOT NULL DEFAULT ''")
    if "duration_seconds" not in columns:
        connection.execute("ALTER TABLE run_attempts ADD COLUMN duration_seconds REAL")
    if "parsed_metrics_json" not in columns:
        connection.execute("ALTER TABLE run_attempts ADD COLUMN parsed_metrics_json TEXT NOT NULL DEFAULT '{}'")
    if "decision_reason" not in columns:
        connection.execute("ALTER TABLE run_attempts ADD COLUMN decision_reason TEXT NOT NULL DEFAULT ''")
    if "per_rule_results_json" not in columns:
        connection.execute("ALTER TABLE run_attempts ADD COLUMN per_rule_results_json TEXT NOT NULL DEFAULT '[]'")


def init_db() -> Path:
    db_path = get_db_path()
    with sqlite3.connect(db_path) as connection:
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS runs (
              test_id TEXT PRIMARY KEY,
              run_status TEXT NOT NULL DEFAULT '',
              execution_mode TEXT NOT NULL DEFAULT '',
              run_kind TEXT NOT NULL DEFAULT 'full_period',
              parent_candidate_id TEXT NOT NULL DEFAULT '',
              split_id TEXT NOT NULL DEFAULT '',
              task_name TEXT NOT NULL,
              ea TEXT NOT NULL,
              symbol TEXT NOT NULL,
              timeframe TEXT NOT NULL,
              date_range TEXT NOT NULL,
              deposit REAL NOT NULL,
              model TEXT NOT NULL,
              full_inputs_json TEXT NOT NULL,
              parsed_metrics_json TEXT NOT NULL,
              pass_fail INTEGER NOT NULL,
              rejection_reason TEXT NOT NULL,
              decision_reason TEXT NOT NULL DEFAULT '',
              per_rule_results_json TEXT NOT NULL DEFAULT '[]',
              raw_report_path TEXT NOT NULL,
              parsed_report_path TEXT NOT NULL DEFAULT '',
              screenshot_path TEXT NOT NULL,
              created_at TEXT NOT NULL
            )
            """
        )
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS run_attempts (
              attempt_id TEXT PRIMARY KEY,
              test_id TEXT NOT NULL,
              run_status TEXT NOT NULL,
              execution_mode TEXT NOT NULL,
              run_kind TEXT NOT NULL,
              parent_candidate_id TEXT NOT NULL,
              split_id TEXT NOT NULL,
              task_name TEXT NOT NULL,
              raw_report_path TEXT NOT NULL,
              parsed_report_path TEXT NOT NULL,
              log_path TEXT NOT NULL,
              set_path TEXT NOT NULL,
              ini_path TEXT NOT NULL,
              command_line TEXT NOT NULL DEFAULT '',
              expected_report_path TEXT NOT NULL DEFAULT '',
              discovered_report_path TEXT NOT NULL DEFAULT '',
              process_id INTEGER,
              process_exit_code INTEGER,
              process_started_at TEXT NOT NULL DEFAULT '',
              process_ended_at TEXT NOT NULL DEFAULT '',
              duration_seconds REAL,
              parsed_metrics_json TEXT NOT NULL DEFAULT '{}',
              decision_reason TEXT NOT NULL DEFAULT '',
              per_rule_results_json TEXT NOT NULL DEFAULT '[]',
              error TEXT NOT NULL,
              created_at TEXT NOT NULL
            )
            """
        )
        _ensure_run_columns(connection)
        _ensure_attempt_columns(connection)
    return db_path


def make_test_id(task_name: str) -> str:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    safe_name = "".join(char if char.isalnum() else "_" for char in task_name).strip("_") or "task"
    return f"{safe_name}_{stamp}"


def _payload_to_metrics(payload: dict[str, Any]) -> dict[str, Any]:
    normalized = payload.get("normalized_metrics")
    if isinstance(normalized, dict):
        return normalized
    return {field_name: payload.get(field_name) for field_name in CORE_METRIC_FIELDS}


def _is_metrics_payload_empty(payload: dict[str, Any]) -> bool:
    if not payload:
        return True
    metrics = _payload_to_metrics(payload)
    return all(metrics.get(field_name) is None for field_name in CORE_METRIC_FIELDS)


def maybe_reparse_report_payload(raw_report_path: str, existing_payload: dict[str, Any]) -> dict[str, Any]:
    if not raw_report_path or not _is_metrics_payload_empty(existing_payload):
        return existing_payload
    path = Path(raw_report_path)
    if not path.exists():
        return existing_payload
    try:
        return parsed_report_to_payload(parse_report_file(path))
    except Exception:
        return existing_payload


def evaluate_acceptance(parsed_report: ParsedReport, acceptance) -> AcceptanceEvaluation:
    metrics = normalized_metrics_payload(parsed_report)
    per_rule_results: list[dict[str, Any]] = []
    missing_metrics: list[str] = []

    def append_rule(
        *,
        rule_name: str,
        metric_name: str,
        threshold: Any,
        actual: Any,
        comparator: str,
        ok: bool,
        missing: bool = False,
    ) -> None:
        per_rule_results.append(
            {
                "rule": rule_name,
                "metric": metric_name,
                "threshold": threshold,
                "actual": actual,
                "comparator": comparator,
                "ok": ok,
                "missing": missing,
            }
        )
        if missing:
            missing_metrics.append(metric_name)

    net_profit = metrics.get("net_profit")
    append_rule(
        rule_name="MIN_PROFIT",
        metric_name="net_profit",
        threshold=acceptance.min_profit,
        actual=net_profit,
        comparator=">=",
        ok=net_profit is not None and net_profit >= acceptance.min_profit,
        missing=net_profit is None,
    )

    profit_factor = metrics.get("profit_factor")
    append_rule(
        rule_name="MIN_PROFIT_FACTOR",
        metric_name="profit_factor",
        threshold=acceptance.min_profit_factor,
        actual=profit_factor,
        comparator=">=",
        ok=profit_factor is not None and profit_factor >= acceptance.min_profit_factor,
        missing=profit_factor is None,
    )

    drawdown_metric = "equity_drawdown_pct" if metrics.get("equity_drawdown_pct") is not None else "relative_drawdown_pct"
    drawdown = metrics.get(drawdown_metric)
    append_rule(
        rule_name="MAX_EQUITY_DD_PCT",
        metric_name=drawdown_metric,
        threshold=acceptance.max_equity_dd_pct,
        actual=drawdown,
        comparator="<=",
        ok=drawdown is not None and drawdown <= acceptance.max_equity_dd_pct,
        missing=drawdown is None,
    )

    total_trades = metrics.get("total_trades")
    append_rule(
        rule_name="MIN_TRADES",
        metric_name="total_trades",
        threshold=acceptance.min_trades,
        actual=total_trades,
        comparator=">=",
        ok=total_trades is not None and total_trades >= acceptance.min_trades,
        missing=total_trades is None,
    )

    failing_rules = [item["rule"] for item in per_rule_results if not item["ok"] and not item["missing"]]
    unique_missing = list(dict.fromkeys(missing_metrics))
    metrics_used = {
        "net_profit": net_profit,
        "profit_factor": profit_factor,
        drawdown_metric: drawdown,
        "total_trades": total_trades,
    }

    if unique_missing:
        decision_reason = f"Missing acceptance metrics: {', '.join(unique_missing)}"
        return AcceptanceEvaluation(
            passed=False,
            status="FAIL_WITH_MISSING_METRICS",
            rejection_reason=";".join(item["rule"] for item in per_rule_results if item["missing"]),
            decision_reason=decision_reason,
            per_rule_results=per_rule_results,
            missing_metrics=unique_missing,
            metrics_used=metrics_used,
        )

    if failing_rules:
        decision_reason = f"Acceptance rules failed: {', '.join(failing_rules)}"
        return AcceptanceEvaluation(
            passed=False,
            status="FAIL",
            rejection_reason=";".join(failing_rules),
            decision_reason=decision_reason,
            per_rule_results=per_rule_results,
            missing_metrics=[],
            metrics_used=metrics_used,
        )

    return AcceptanceEvaluation(
        passed=True,
        status="PASS",
        rejection_reason="",
        decision_reason="All acceptance rules passed.",
        per_rule_results=per_rule_results,
        missing_metrics=[],
        metrics_used=metrics_used,
    )


def store_run(record: StoredRun) -> Path:
    db_path = init_db()
    with sqlite3.connect(db_path) as connection:
        connection.execute(
            """
            INSERT OR REPLACE INTO runs (
              test_id, run_status, execution_mode, run_kind, parent_candidate_id, split_id, task_name, ea, symbol, timeframe, date_range, deposit, model,
              full_inputs_json, parsed_metrics_json, pass_fail, rejection_reason, decision_reason, per_rule_results_json,
              raw_report_path, parsed_report_path, screenshot_path, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                record.test_id,
                record.run_status,
                record.execution_mode,
                record.run_kind,
                record.parent_candidate_id,
                record.split_id,
                record.task_name,
                record.ea,
                record.symbol,
                record.timeframe,
                record.date_range,
                record.deposit,
                record.model,
                json.dumps(record.full_inputs_json, sort_keys=True),
                json.dumps(record.parsed_metrics_json, sort_keys=True),
                1 if record.passed else 0,
                record.rejection_reason,
                record.decision_reason,
                json.dumps(record.per_rule_results, sort_keys=True),
                record.raw_report_path,
                record.parsed_report_path,
                record.screenshot_path,
                record.created_at,
            ),
        )
    return db_path


def make_attempt_id(test_id: str, run_status: str) -> str:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    return f"{test_id}_{run_status}_{stamp}"


def store_run_attempt(record: RunAttempt) -> Path:
    db_path = init_db()
    with sqlite3.connect(db_path) as connection:
        connection.execute(
            """
            INSERT INTO run_attempts (
              attempt_id, test_id, run_status, execution_mode, run_kind, parent_candidate_id, split_id,
              task_name, raw_report_path, parsed_report_path, log_path, set_path, ini_path,
              command_line, expected_report_path, discovered_report_path, process_id, process_exit_code,
              process_started_at, process_ended_at, duration_seconds, parsed_metrics_json, decision_reason,
              per_rule_results_json, error, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                record.attempt_id,
                record.test_id,
                record.run_status,
                record.execution_mode,
                record.run_kind,
                record.parent_candidate_id,
                record.split_id,
                record.task_name,
                record.raw_report_path,
                record.parsed_report_path,
                record.log_path,
                record.set_path,
                record.ini_path,
                record.command_line,
                record.expected_report_path,
                record.discovered_report_path,
                record.process_id,
                record.process_exit_code,
                record.process_started_at,
                record.process_ended_at,
                record.duration_seconds,
                json.dumps(record.parsed_metrics_json, sort_keys=True),
                record.decision_reason,
                json.dumps(record.per_rule_results, sort_keys=True),
                record.error,
                record.created_at,
            ),
        )
    return db_path


def _decode_json_field(value: Any, default: Any) -> Any:
    if not value:
        return default
    if isinstance(value, (dict, list)):
        return value
    try:
        return json.loads(value)
    except (TypeError, json.JSONDecodeError):
        return default


def _hydrate_run_row(row: dict[str, Any]) -> dict[str, Any]:
    payload = _decode_json_field(row.get("parsed_metrics_json"), {})
    payload = maybe_reparse_report_payload(str(row.get("raw_report_path", "")), payload)
    row["parsed_metrics_json"] = json.dumps(payload, sort_keys=True)
    row["parsed_metrics_payload"] = payload
    row["per_rule_results"] = _decode_json_field(row.get("per_rule_results_json"), [])
    row["effective_run_status"] = row.get("run_status", "")
    row["effective_pass_fail"] = bool(row.get("pass_fail"))
    row["effective_rejection_reason"] = row.get("rejection_reason", "")
    row["effective_decision_reason"] = row.get("decision_reason", "")
    row["effective_per_rule_results"] = row["per_rule_results"]

    acceptance = _load_acceptance_for_test(row["test_id"])
    if acceptance is not None and row.get("raw_report_path") and Path(str(row["raw_report_path"])).exists():
        try:
            evaluation = evaluate_acceptance(parse_report_file(str(row["raw_report_path"])), acceptance)
            row["effective_run_status"] = evaluation.status
            row["effective_pass_fail"] = evaluation.passed
            row["effective_rejection_reason"] = evaluation.rejection_reason
            row["effective_decision_reason"] = evaluation.decision_reason
            row["effective_per_rule_results"] = evaluation.per_rule_results
        except Exception:
            pass
    return row


def _hydrate_attempt_row(row: dict[str, Any]) -> dict[str, Any]:
    row["parsed_metrics_payload"] = _decode_json_field(row.get("parsed_metrics_json"), {})
    row["per_rule_results"] = _decode_json_field(row.get("per_rule_results_json"), [])
    return row


def _load_acceptance_for_test(test_id: str):
    db_path = init_db()
    with sqlite3.connect(db_path) as connection:
        connection.row_factory = sqlite3.Row
        row = connection.execute(
            "SELECT log_path FROM run_attempts WHERE test_id = ? ORDER BY created_at DESC LIMIT 1",
            (test_id,),
        ).fetchone()
    if row is None:
        return None
    log_path = str(row["log_path"] or "")
    if not log_path:
        return None
    path = Path(log_path)
    if not path.exists():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    task_payload = payload.get("task")
    if not isinstance(task_payload, dict):
        return None
    return validate_task_payload(task_payload).acceptance


def fetch_run_attempts(test_id: str | None = None) -> list[dict[str, Any]]:
    db_path = init_db()
    query = "SELECT * FROM run_attempts"
    params: tuple[Any, ...] = ()
    if test_id is not None:
        query += " WHERE test_id = ?"
        params = (test_id,)
    query += " ORDER BY created_at ASC"
    with sqlite3.connect(db_path) as connection:
        connection.row_factory = sqlite3.Row
        rows = connection.execute(query, params).fetchall()
    return [_hydrate_attempt_row(dict(row)) for row in rows]


def fetch_latest_run_attempt(test_id: str) -> dict[str, Any] | None:
    attempts = fetch_run_attempts(test_id)
    return attempts[-1] if attempts else None


def fetch_run(test_id: str) -> dict[str, Any] | None:
    db_path = init_db()
    with sqlite3.connect(db_path) as connection:
        connection.row_factory = sqlite3.Row
        row = connection.execute("SELECT * FROM runs WHERE test_id = ?", (test_id,)).fetchone()
    return _hydrate_run_row(dict(row)) if row is not None else None


def fetch_runs() -> list[dict[str, Any]]:
    db_path = init_db()
    with sqlite3.connect(db_path) as connection:
        connection.row_factory = sqlite3.Row
        rows = connection.execute(
            """
            SELECT *
            FROM runs
            ORDER BY pass_fail DESC,
                     json_extract(parsed_metrics_json, '$.profit_factor') DESC,
                     json_extract(parsed_metrics_json, '$.net_profit') DESC,
                     created_at DESC
            """
        ).fetchall()
    return [_hydrate_run_row(dict(row)) for row in rows]


def update_leaderboard_csv() -> Path:
    rows = fetch_runs()
    output_path = get_leaderboard_path()
    fieldnames = [
        "test_id",
        "run_status",
        "execution_mode",
        "run_kind",
        "parent_candidate_id",
        "split_id",
        "task_name",
        "ea",
        "symbol",
        "timeframe",
        "date_range",
        "deposit",
        "model",
        "pass_fail",
        "rejection_reason",
        "decision_reason",
        "net_profit",
        "profit_factor",
        "relative_drawdown_pct",
        "equity_drawdown_pct",
        "total_trades",
        "parser_warnings",
        "created_at",
    ]
    with output_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            payload = row["parsed_metrics_payload"]
            metrics = _payload_to_metrics(payload)
            writer.writerow(
                {
                    "test_id": row["test_id"],
                    "run_status": row.get("effective_run_status", row["run_status"]),
                    "execution_mode": row["execution_mode"],
                    "run_kind": row["run_kind"],
                    "parent_candidate_id": row["parent_candidate_id"],
                    "split_id": row["split_id"],
                    "task_name": row["task_name"],
                    "ea": row["ea"],
                    "symbol": row["symbol"],
                    "timeframe": row["timeframe"],
                    "date_range": row["date_range"],
                    "deposit": row["deposit"],
                    "model": row["model"],
                    "pass_fail": "PASS" if row.get("effective_pass_fail", row["pass_fail"]) else "FAIL",
                    "rejection_reason": row.get("effective_rejection_reason", row["rejection_reason"]),
                    "decision_reason": row.get("effective_decision_reason", row.get("decision_reason", "")),
                    "net_profit": metrics.get("net_profit"),
                    "profit_factor": metrics.get("profit_factor"),
                    "relative_drawdown_pct": metrics.get("relative_drawdown_pct"),
                    "equity_drawdown_pct": metrics.get("equity_drawdown_pct"),
                    "total_trades": metrics.get("total_trades"),
                    "parser_warnings": " | ".join(payload.get("parser_warnings", [])),
                    "created_at": row["created_at"],
                }
            )
    return output_path


def update_summary_md() -> Path:
    rows = fetch_runs()
    output_path = get_summary_path()
    lines = ["# MT5 Research Agent Summary", ""]
    if not rows:
        lines.append("No stored runs yet.")
    else:
        lines.append("| Test ID | Status | Mode | Pass/Fail | PF | Net Profit | DD % | Trades | Parser Warnings | Decision | Reason |")
        lines.append("| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |")
        for row in rows[:20]:
            payload = row["parsed_metrics_payload"]
            metrics = _payload_to_metrics(payload)
            warnings = payload.get("parser_warnings", [])
            lines.append(
                f"| {row['test_id']} | {row.get('effective_run_status', row['run_status']) or '-'} | {row['execution_mode'] or '-'} | {'PASS' if row.get('effective_pass_fail', row['pass_fail']) else 'FAIL'} | "
                f"{metrics.get('profit_factor')} | {metrics.get('net_profit')} | "
                f"{metrics.get('equity_drawdown_pct') if metrics.get('equity_drawdown_pct') is not None else metrics.get('relative_drawdown_pct')} | "
                f"{metrics.get('total_trades')} | {'; '.join(warnings) if warnings else '-'} | "
                f"{row.get('effective_decision_reason', row.get('decision_reason')) or '-'} | {row.get('effective_rejection_reason', row['rejection_reason']) or '-'} |"
            )
    output_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return output_path


def store_parsed_report_json(test_id: str, parsed_report: ParsedReport) -> Path:
    output_path = get_parsed_reports_dir() / f"{test_id}.json"
    output_path.write_text(json.dumps(parsed_report_to_payload(parsed_report), indent=2), encoding="utf-8")
    return output_path


def build_stored_run(
    *,
    test_id: str,
    task,
    parsed_report: ParsedReport | None,
    passed: bool,
    rejection_reason: str,
    decision_reason: str = "",
    per_rule_results: list[dict[str, Any]] | None = None,
    raw_report_path: str,
    parsed_report_path: str = "",
    screenshot_path: str,
    run_status: str = "",
    execution_mode: str = "",
    run_kind: str = "full_period",
    parent_candidate_id: str = "",
    split_id: str = "",
) -> StoredRun:
    date_range = f"{task.period_from} - {task.period_to}"
    parsed_metrics = parsed_report_to_payload(parsed_report) if parsed_report is not None else {}
    return StoredRun(
        test_id=test_id,
        run_status=run_status,
        execution_mode=execution_mode,
        run_kind=run_kind,
        parent_candidate_id=parent_candidate_id,
        split_id=split_id,
        task_name=task.name,
        ea=task.ea,
        symbol=task.symbol,
        timeframe=task.timeframe,
        date_range=date_range,
        deposit=task.deposit,
        model=task.model,
        full_inputs_json=task.inputs,
        parsed_metrics_json=parsed_metrics,
        passed=passed,
        rejection_reason=rejection_reason,
        decision_reason=decision_reason,
        per_rule_results=per_rule_results or [],
        raw_report_path=raw_report_path,
        parsed_report_path=parsed_report_path,
        screenshot_path=screenshot_path,
        created_at=datetime.now(timezone.utc).isoformat(),
    )
