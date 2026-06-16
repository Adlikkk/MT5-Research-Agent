from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from mt5_research_agent.background_runner import read_log_payload
from mt5_research_agent.report_parser import parse_report_file, parsed_report_to_payload
from mt5_research_agent.result_store import (
    evaluate_acceptance,
    fetch_latest_run_attempt,
    fetch_run,
    get_parsed_reports_dir,
    update_leaderboard_csv,
    update_summary_md,
)
from mt5_research_agent.split_validation import summarize_candidate
from mt5_research_agent.task import validate_task_payload


def _extract_acceptance(test_id: str) -> tuple[Any | None, dict[str, Any]]:
    attempt = fetch_latest_run_attempt(test_id)
    log_payload = read_log_payload(str((attempt or {}).get("log_path", ""))) or {}
    task_payload = log_payload.get("task")
    if isinstance(task_payload, dict):
        task = validate_task_payload(task_payload)
        return task.acceptance, log_payload
    return None, log_payload


def _load_report_for_test(test_id: str):
    run_row = fetch_run(test_id)
    if run_row is None:
        return None, None
    raw_report_path = str(run_row.get("raw_report_path", "") or "")
    if raw_report_path and Path(raw_report_path).exists():
        return parse_report_file(raw_report_path), run_row
    return None, run_row


def run_parse_report_command(report_path: str) -> int:
    try:
        path = Path(report_path)
        report = parse_report_file(path)
        output_path = get_parsed_reports_dir() / f"{path.stem}.json"
        payload = parsed_report_to_payload(report)
        output_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        print(f"metric keys: {', '.join(payload['normalized_metrics'].keys())}")
        for key, value in payload["normalized_metrics"].items():
            print(f"{key}: {value}")
        print("parser warnings:")
        if payload["parser_warnings"]:
            for warning in payload["parser_warnings"]:
                print(f"- {warning}")
        else:
            print("- none")
        print(f"output json: {output_path}")
        return 0
    except Exception as exc:
        print(str(exc))
        return 1


def run_explain_decision_command(test_id: str) -> int:
    acceptance, log_payload = _extract_acceptance(test_id)
    report, run_row = _load_report_for_test(test_id)
    if run_row is None:
        print(f"No stored run found for test_id: {test_id}")
        return 1
    if acceptance is None:
        print(f"No acceptance rules found for test_id: {test_id}")
        return 1
    if report is None:
        print(f"No raw report available for test_id: {test_id}")
        return 1

    evaluation = evaluate_acceptance(report, acceptance)
    payload = parsed_report_to_payload(report)

    print(f"test_id: {test_id}")
    print(f"status: {run_row.get('run_status') or '<unknown>'}")
    print(
        "acceptance rules: "
        f"min_profit={acceptance.min_profit}, "
        f"min_profit_factor={acceptance.min_profit_factor}, "
        f"max_equity_dd_pct={acceptance.max_equity_dd_pct}, "
        f"min_trades={acceptance.min_trades}"
    )
    print("parsed metrics used:")
    for key, value in evaluation.metrics_used.items():
        print(f"- {key}: {value}")
    print("rule checks:")
    for item in evaluation.per_rule_results:
        print(
            f"- {item['rule']}: ok={item['ok']} missing={item['missing']} "
            f"metric={item['metric']} actual={item['actual']} {item['comparator']} threshold={item['threshold']}"
        )
    print(f"final decision: {evaluation.status}")
    print(f"decision reason: {evaluation.decision_reason}")
    print("missing metrics:")
    if evaluation.missing_metrics:
        for metric in evaluation.missing_metrics:
            print(f"- {metric}")
    else:
        print("- none")
    print("parser warnings:")
    if payload["parser_warnings"]:
        for warning in payload["parser_warnings"]:
            print(f"- {warning}")
    else:
        print("- none")
    if log_payload:
        latest_attempt = fetch_latest_run_attempt(test_id)
        if latest_attempt is not None:
            print(f"log path: {latest_attempt.get('log_path', '')}")
    return 0


def run_leaderboard_command() -> int:
    path = update_leaderboard_csv()
    print(f"leaderboard: {path}")
    return 0


def run_summarize_command() -> int:
    path = update_summary_md()
    print(f"summary: {path}")
    return 0


def run_summarize_candidate_command(candidate_id: str) -> int:
    path = summarize_candidate(candidate_id)
    print(f"candidate summary: {path}")
    return 0
