from __future__ import annotations

import itertools
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from mt5_research_agent.config import load_config
from mt5_research_agent.experiment import generated_tasks_dir
from mt5_research_agent.report_parser import metrics_drawdown_pct
from mt5_research_agent.research_workflow import ParsedResearchRequest, parse_research_request, write_research_plan
from mt5_research_agent.result_store import fetch_runs, update_leaderboard_csv, update_summary_md
from mt5_research_agent.run_task import execute_run_task
from mt5_research_agent.split_validation import evaluate_split_row
from mt5_research_agent.task import load_task


@dataclass(slots=True)
class CandidateAssessment:
    test_id: str
    task_name: str
    inputs: dict[str, str]
    full_row: dict[str, Any]
    split_rows: list[dict[str, Any]]
    hard_rejection_reasons: list[str]
    score: float | None


def utc_stamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def plans_dir() -> Path:
    config = load_config()
    path = Path(config.artifacts_dir).resolve() / "plans"
    path.mkdir(parents=True, exist_ok=True)
    return path


def generated_experiments_dir() -> Path:
    config = load_config()
    path = Path(config.artifacts_dir).resolve() / "generated_experiments"
    path.mkdir(parents=True, exist_ok=True)
    return path


def load_request_runs(request: ParsedResearchRequest) -> tuple[list[dict[str, Any]], dict[str, list[dict[str, Any]]]]:
    rows = fetch_runs()
    full_rows = [
        row
        for row in rows
        if row.get("run_kind") == "full_period" and str(row.get("task_name", "")).startswith(request.slug)
    ]
    split_map: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        if row.get("run_kind") != "split":
            continue
        parent_id = str(row.get("parent_candidate_id", "")).strip()
        if not parent_id:
            continue
        split_map.setdefault(parent_id, []).append(row)
    return full_rows, split_map


def parse_metrics(row: dict[str, Any]) -> dict[str, Any]:
    return json.loads(row["parsed_metrics_json"]) if row.get("parsed_metrics_json") else {}


def hard_rejection_reasons_for_candidate(
    request: ParsedResearchRequest,
    full_row: dict[str, Any],
    split_rows: list[dict[str, Any]],
) -> list[str]:
    reasons: list[str] = []
    if request.split_acceptance is None:
        reasons.append("MISSING_SPLIT_ACCEPTANCE")
        return reasons
    if full_row.get("rejection_reason") == "REPORT_MISSING" or not full_row.get("raw_report_path"):
        reasons.append("MISSING_REPORT")
    if not split_rows:
        reasons.append("MISSING_SPLITS")
        return reasons

    for split_row in split_rows:
        if split_row.get("rejection_reason") == "REPORT_MISSING" or not split_row.get("raw_report_path"):
            reasons.append("MISSING_REPORT")
            break
        passed, split_reasons = evaluate_split_row(split_row, request.split_acceptance)
        if not passed:
            reasons.extend(split_reasons)
    return sorted(set(reasons))


def candidate_score(request: ParsedResearchRequest, full_row: dict[str, Any], split_rows: list[dict[str, Any]]) -> float | None:
    hard_reasons = hard_rejection_reasons_for_candidate(request, full_row, split_rows)
    if hard_reasons:
        return None
    split_acceptance = request.split_acceptance
    if split_acceptance is None:
        return None

    full_metrics = parse_metrics(full_row)
    split_metrics = [parse_metrics(row) for row in split_rows]
    profit_factors = [float(metrics.get("profit_factor") or 0) for metrics in split_metrics]
    drawdowns = [float(metrics_drawdown_pct(metrics) or 9999) for metrics in split_metrics]
    net_profits = [float(metrics.get("net_profit") or 0) for metrics in split_metrics]
    trades = [float(metrics.get("total_trades") or 0) for metrics in split_metrics]

    pf_stability = min(profit_factors) / max(profit_factors) if max(profit_factors) > 0 else 0.0
    max_dd = max(drawdowns) if drawdowns else 9999.0
    dd_headroom = max(0.0, min(1.0, 1 - (max_dd / split_acceptance.max_equity_dd_pct_each_split)))
    weak_period_survival = min(
        min(profit_factors) / split_acceptance.min_profit_factor_each_split,
        min(net_profits) / 1.0 if min(net_profits) > 0 else 0.0,
    )
    weak_period_survival = max(0.0, min(1.0, weak_period_survival))
    full_profit = float(full_metrics.get("net_profit") or 0)
    profit_score = max(0.0, min(1.0, full_profit / max(full_profit, 1.0)))
    trades_headroom = max(0.0, min(1.0, (min(trades) if trades else 0) / split_acceptance.min_trades_each_split))

    return round(
        (pf_stability * 35.0)
        + (dd_headroom * 25.0)
        + (weak_period_survival * 25.0)
        + (profit_score * 10.0)
        + (trades_headroom * 5.0),
        4,
    )


def assess_candidates(request: ParsedResearchRequest) -> list[CandidateAssessment]:
    full_rows, split_map = load_request_runs(request)
    assessments: list[CandidateAssessment] = []
    for full_row in full_rows:
        test_id = str(full_row["test_id"])
        split_rows = sorted(split_map.get(test_id, []), key=lambda row: row["split_id"])
        inputs = json.loads(full_row["full_inputs_json"])
        hard_reasons = hard_rejection_reasons_for_candidate(request, full_row, split_rows)
        score = candidate_score(request, full_row, split_rows)
        assessments.append(
            CandidateAssessment(
                test_id=test_id,
                task_name=str(full_row["task_name"]),
                inputs=inputs,
                full_row=full_row,
                split_rows=split_rows,
                hard_rejection_reasons=hard_reasons,
                score=score,
            )
        )
    assessments.sort(key=lambda item: (item.score is not None, item.score or -1, item.test_id), reverse=True)
    return assessments


def parameter_value_stats(assessments: list[CandidateAssessment], parameter_space: dict[str, list[str]]) -> dict[str, dict[str, dict[str, float]]]:
    stats: dict[str, dict[str, dict[str, float]]] = {name: {} for name in parameter_space}
    for name, values in parameter_space.items():
        for value in values:
            matching = [item for item in assessments if item.inputs.get(name) == value]
            total = len(matching)
            passing = len([item for item in matching if item.score is not None])
            avg_score = sum(item.score or 0.0 for item in matching) / total if total else 0.0
            stats[name][value] = {
                "total": float(total),
                "passing": float(passing),
                "pass_rate": (passing / total) if total else 0.0,
                "avg_score": avg_score,
            }
    return stats


def weak_parameter_values(stats: dict[str, dict[str, dict[str, float]]]) -> dict[str, list[str]]:
    weak: dict[str, list[str]] = {}
    for name, value_stats in stats.items():
        weak[name] = [
            value
            for value, entry in value_stats.items()
            if entry["total"] >= 2 and entry["pass_rate"] <= 0.25
        ]
    return weak


def failed_parameter_zones(stats: dict[str, dict[str, dict[str, float]]]) -> dict[str, list[str]]:
    zones: dict[str, list[str]] = {}
    for name, value_stats in stats.items():
        zones[name] = [
            value
            for value, entry in value_stats.items()
            if entry["total"] >= 2 and entry["passing"] == 0
        ]
    return zones


def neighbor_values(all_values: list[str], selected: str) -> list[str]:
    if selected not in all_values:
        return [selected]
    index = all_values.index(selected)
    values = [all_values[index]]
    if index > 0:
        values.append(all_values[index - 1])
    if index + 1 < len(all_values):
        values.append(all_values[index + 1])
    # preserve original ordering
    ordered: list[str] = []
    for value in all_values:
        if value in values and value not in ordered:
            ordered.append(value)
    return ordered


def build_candidate_combo_pool(
    request: ParsedResearchRequest,
    assessments: list[CandidateAssessment],
) -> tuple[list[dict[str, str]], dict[str, list[str]], dict[str, list[str]]]:
    stats = parameter_value_stats(assessments, request.parameter_space)
    weak_values = weak_parameter_values(stats)
    avoid_values = failed_parameter_zones(stats)

    robust = [item for item in assessments if item.score is not None]
    seeds = robust[:2]
    combos: list[dict[str, str]] = []

    if not seeds:
        for product in itertools.product(*(request.parameter_space[key] for key in request.parameter_space)):
            combo = {key: value for key, value in zip(request.parameter_space, product, strict=True)}
            combos.append(combo)
        return combos, weak_values, avoid_values

    for seed in seeds:
        local_space: dict[str, list[str]] = {}
        for name, values in request.parameter_space.items():
            local_space[name] = neighbor_values(values, seed.inputs[name])
        for product in itertools.product(*(local_space[key] for key in request.parameter_space)):
            combo = {key: value for key, value in zip(request.parameter_space, product, strict=True)}
            combos.append(combo)

    unique: list[dict[str, str]] = []
    seen: set[tuple[tuple[str, str], ...]] = set()
    for combo in combos:
        key = tuple(sorted(combo.items()))
        if key in seen:
            continue
        seen.add(key)
        unique.append(combo)
    return unique, weak_values, avoid_values


def filter_planned_combos(
    request: ParsedResearchRequest,
    combos: list[dict[str, str]],
    assessments: list[CandidateAssessment],
    avoid_values: dict[str, list[str]],
    limit: int,
) -> list[dict[str, str]]:
    tested = {tuple(sorted(item.inputs.items())) for item in assessments}
    planned: list[dict[str, str]] = []
    for combo in combos:
        combo_key = tuple(sorted(combo.items()))
        if combo_key in tested:
            continue
        if any(combo.get(name) in values for name, values in avoid_values.items() if values):
            continue
        planned.append(combo)
        if len(planned) >= limit:
            break
    return planned


def planned_experiment_payload(
    request: ParsedResearchRequest,
    combos: list[dict[str, str]],
    task_path: Path,
    stamp: str,
) -> dict[str, Any]:
    return {
        "name": f"{request.slug}_planned_{stamp.lower()}",
        "request_slug": request.slug,
        "base_task": str(task_path),
        "limits": {
            "max_tests": len(combos),
            "stop_after_failures": request.experiment_limits["stop_after_failures"],
        },
        "tasks": combos,
    }


def render_plan_markdown(
    request: ParsedResearchRequest,
    assessments: list[CandidateAssessment],
    planned_combos: list[dict[str, str]],
    weak_values: dict[str, list[str]],
    avoid_values: dict[str, list[str]],
    plan_path: Path,
    experiment_path: Path,
) -> str:
    robust = [item for item in assessments if item.score is not None]
    lines = [
        f"# Planner {plan_path.stem}",
        "",
        f"- Request slug: {request.slug}",
        f"- Source request: {request.source_path}",
        f"- Generated experiment: {experiment_path}",
        f"- Proposed tests: {len(planned_combos)}",
        "",
        "## Best Passing Candidates",
        "",
    ]
    if robust:
        lines.append("| Test ID | Score | Inputs | Hard Rejections |")
        lines.append("| --- | --- | --- | --- |")
        for item in robust[:5]:
            lines.append(
                f"| {item.test_id} | {item.score} | `{json.dumps(item.inputs, sort_keys=True)}` | {', '.join(item.hard_rejection_reasons) or '-'} |"
            )
    else:
        lines.append("No robust split-passing candidates yet. Falling back to full request parameter space.")

    lines.extend(["", "## Weak Parameters", ""])
    for name in request.parameter_space:
        lines.append(f"- {name}: {weak_values.get(name) or ['none']}")

    lines.extend(["", "## Failed Zones To Avoid", ""])
    for name in request.parameter_space:
        lines.append(f"- {name}: {avoid_values.get(name) or ['none']}")

    lines.extend(["", "## Nearby Robustness Tests", ""])
    if planned_combos:
        for combo in planned_combos:
            lines.append(f"- {json.dumps(combo, sort_keys=True)}")
    else:
        lines.append("- No untested nearby combinations remained after filtering.")
    return "\n".join(lines) + "\n"


def build_next_plan(request: ParsedResearchRequest) -> tuple[Path, Path]:
    if request.todos:
        raise ValueError("Research request is ambiguous. Run plan-from-request and resolve TODOs first.")
    artifacts = write_research_plan(request)
    if artifacts.task_path is None:
        raise RuntimeError("Expected a generated base task path for a fully specified research request.")
    assessments = assess_candidates(request)
    combos, weak_values, avoid_values = build_candidate_combo_pool(request, assessments)
    planned_combos = filter_planned_combos(
        request,
        combos,
        assessments,
        avoid_values,
        limit=min(request.experiment_limits["max_tests"], 12),
    )
    if not planned_combos and not assessments:
        planned_combos = combos[: min(request.experiment_limits["max_tests"], len(combos))]
    if not planned_combos:
        raise ValueError("No untested planned combinations remained after filtering.")

    stamp = utc_stamp()
    experiment_payload = planned_experiment_payload(request, planned_combos, artifacts.task_path, stamp)
    experiment_path = generated_experiments_dir() / f"experiment_{stamp}.json"
    experiment_path.write_text(json.dumps(experiment_payload, indent=2), encoding="utf-8")

    plan_path = plans_dir() / f"plan_{stamp}.md"
    plan_path.write_text(
        render_plan_markdown(
            request,
            assessments,
            planned_combos,
            weak_values,
            avoid_values,
            plan_path,
            experiment_path,
        ),
        encoding="utf-8",
    )
    return plan_path, experiment_path


def run_plan_next_command(request_path: str) -> int:
    try:
        request = parse_research_request(request_path)
        plan_path, experiment_path = build_next_plan(request)
    except Exception as exc:
        print(str(exc))
        return 1
    print(f"plan: {plan_path}")
    print(f"experiment: {experiment_path}")
    return 0


def load_planned_experiment(experiment_path: str | Path) -> dict[str, Any]:
    path = Path(experiment_path)
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("Planned experiment file must contain a JSON object.")
    tasks = payload.get("tasks")
    if not isinstance(tasks, list) or not tasks:
        raise ValueError("Planned experiment file must contain a non-empty `tasks` list.")
    base_task = payload.get("base_task")
    if not isinstance(base_task, str) or not base_task.strip():
        raise ValueError("Planned experiment file must contain `base_task`.")
    return payload


def run_planned_command(experiment_path: str, allow_gui_clicks: bool, timeout_seconds: int = 1800) -> int:
    try:
        payload = load_planned_experiment(experiment_path)
        base_task = load_task(payload["base_task"])
        tasks_dir = generated_tasks_dir() / str(payload["name"])
        tasks_dir.mkdir(parents=True, exist_ok=True)
        failures = 0

        for index, combo in enumerate(payload["tasks"], start=1):
            if not isinstance(combo, dict) or not combo:
                raise ValueError(f"Task {index} in planned experiment must be a non-empty object.")
            task_payload = {
                "test_id": f"{payload['name'].upper()}-{index:04d}",
                "name": f"{payload['name']}_{index:04d}",
                "ea": base_task.ea,
                "symbol": base_task.symbol,
                "timeframe": base_task.timeframe,
                "period_from": base_task.period_from,
                "period_to": base_task.period_to,
                "deposit": base_task.deposit,
                "model": base_task.model,
                "inputs": {**base_task.inputs, **{str(key): str(value) for key, value in combo.items()}},
                "acceptance": {
                    "min_profit": base_task.acceptance.min_profit,
                    "min_profit_factor": base_task.acceptance.min_profit_factor,
                    "max_equity_dd_pct": base_task.acceptance.max_equity_dd_pct,
                    "min_trades": base_task.acceptance.min_trades,
                },
            }
            task_path = tasks_dir / f"{task_payload['test_id']}.json"
            task_path.write_text(json.dumps(task_payload, indent=2), encoding="utf-8")
            result = execute_run_task(
                str(task_path),
                allow_gui_clicks=allow_gui_clicks,
                timeout_seconds=timeout_seconds,
                execution_mode="cli",
            )
            update_leaderboard_csv()
            update_summary_md()
            if result.exit_code != 0:
                failures += 1
            if result.safety_ui_failure:
                print(f"planned run stopped on safety/UI failure at {task_payload['test_id']}")
                print(f"log: {result.log_path}")
                return 1
            if failures >= int(payload["limits"]["stop_after_failures"]):
                print(f"planned run stopped after {failures} failures")
                return 1

        print(f"planned experiment: {payload['name']}")
        print(f"tasks run: {len(payload['tasks'])}")
        return 0
    except Exception as exc:
        print(str(exc))
        return 1
