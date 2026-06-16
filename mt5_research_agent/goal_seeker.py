"""Phase 4 goal-seeking loop.

Iterates toward a target (for example "+250% over 5 years under 25% drawdown")
by running bounded exploratory batches, ranking candidates, refining around
promising parameter zones, and split-validating the strongest candidates. It
stops when the target is robustly reached, the test budget is exhausted, runtime
runs out, or progress stalls.

Hard safety rules this module must honor:
- It never optimizes for raw profit alone. A candidate is only "robust" when it
  also survives split validation (when the goal requires it) and respects the
  drawdown / profit-factor / trade-count constraints.
- It never claims guaranteed profit and always reports honestly when the target
  was not robustly reached, naming the closest raw candidate and why it was
  rejected.
- It never hides failed attempts; every run is preserved in the result store.
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from mt5_research_agent.experiment import (
    ExperimentLimits,
    ExperimentSpec,
    build_generated_tasks,
    write_generated_tasks,
)
from mt5_research_agent.goal import ResearchGoal
from mt5_research_agent.planner import build_next_plan, load_request_runs
from mt5_research_agent.report_parser import metrics_drawdown_pct
from mt5_research_agent.research_workflow import (
    ParsedResearchRequest,
    build_experiment_payload,
    build_task_payload,
    parse_research_request,
    run_split_validation_for_candidate,
    write_research_plan,
)
from mt5_research_agent.result_store import (
    get_results_dir,
    update_leaderboard_csv,
    update_summary_md,
)
from mt5_research_agent.run_task import execute_run_task
from mt5_research_agent.split_validation import SplitExperiment
from mt5_research_agent.task import validate_task_payload
from mt5_research_agent.planner import load_planned_experiment


@dataclass(slots=True)
class CandidateGoalView:
    test_id: str
    task_name: str
    inputs: dict[str, str]
    return_pct: float | None
    profit_factor: float | None
    drawdown_pct: float | None
    total_trades: int | None
    meets_raw_goal: bool
    raw_reasons: list[str]
    splits_validated: bool | None
    is_robust: bool


@dataclass(slots=True)
class GoalSeekResult:
    slug: str
    target_reached: bool
    best_robust_id: str
    closest_raw_id: str
    tests_run: int
    rounds: int
    stop_reason: str
    report_path: str
    candidates: list[CandidateGoalView] = field(default_factory=list)


def goal_from_request(request: ParsedResearchRequest) -> ResearchGoal:
    """Return the request's explicit goal, or derive a conservative one.

    When a request has no `## Goal constraints` block we still build a goal so
    the loop has a budget and constraints, defaulting from the hard limits.
    """

    if request.goal_constraints is not None:
        return request.goal_constraints
    acceptance = request.acceptance_payload
    return ResearchGoal(
        target_total_return_pct=None,
        max_equity_drawdown_pct=acceptance.get("max_equity_dd_pct"),
        min_profit_factor=acceptance.get("min_profit_factor"),
        min_trades=acceptance.get("min_trades"),
        must_validate_splits=bool(request.splits),
        max_tests=int(request.experiment_limits.get("max_tests", 50)),
    )


def candidate_return_pct(row: dict[str, Any]) -> float | None:
    metrics = json.loads(row["parsed_metrics_json"]) if row.get("parsed_metrics_json") else {}
    net_profit = metrics.get("net_profit")
    deposit = row.get("deposit")
    if net_profit is None or not deposit:
        return None
    return round((float(net_profit) / float(deposit)) * 100.0, 2)


def meets_raw_goal(row: dict[str, Any], goal: ResearchGoal) -> tuple[bool, list[str]]:
    """Check a full-period candidate against the raw (non-split) goal metrics."""

    metrics = json.loads(row["parsed_metrics_json"]) if row.get("parsed_metrics_json") else {}
    reasons: list[str] = []

    if goal.target_total_return_pct is not None:
        return_pct = candidate_return_pct(row)
        if return_pct is None or return_pct < goal.target_total_return_pct:
            reasons.append("BELOW_TARGET_RETURN")
    if goal.max_equity_drawdown_pct is not None:
        drawdown = metrics_drawdown_pct(metrics)
        if drawdown is None or drawdown > goal.max_equity_drawdown_pct:
            reasons.append("EXCEEDS_MAX_DRAWDOWN")
    if goal.min_profit_factor is not None:
        profit_factor = metrics.get("profit_factor")
        if profit_factor is None or profit_factor < goal.min_profit_factor:
            reasons.append("BELOW_MIN_PROFIT_FACTOR")
    if goal.min_trades is not None:
        total_trades = metrics.get("total_trades")
        if total_trades is None or total_trades < goal.min_trades:
            reasons.append("BELOW_MIN_TRADES")
    return (not reasons, reasons)


def splits_validated_for(test_id: str, split_map: dict[str, list[dict[str, Any]]]) -> bool | None:
    rows = split_map.get(test_id)
    if not rows:
        return None
    return all(bool(row.get("pass_fail")) for row in rows)


def build_candidate_views(request: ParsedResearchRequest, goal: ResearchGoal) -> list[CandidateGoalView]:
    full_rows, split_map = load_request_runs(request)
    views: list[CandidateGoalView] = []
    for row in full_rows:
        metrics = json.loads(row["parsed_metrics_json"]) if row.get("parsed_metrics_json") else {}
        meets_raw, raw_reasons = meets_raw_goal(row, goal)
        splits_ok = splits_validated_for(str(row["test_id"]), split_map)
        if goal.must_validate_splits:
            is_robust = bool(meets_raw and splits_ok)
        else:
            is_robust = bool(meets_raw)
        views.append(
            CandidateGoalView(
                test_id=str(row["test_id"]),
                task_name=str(row.get("task_name", "")),
                inputs=json.loads(row["full_inputs_json"]) if row.get("full_inputs_json") else {},
                return_pct=candidate_return_pct(row),
                profit_factor=metrics.get("profit_factor"),
                drawdown_pct=metrics_drawdown_pct(metrics),
                total_trades=metrics.get("total_trades"),
                meets_raw_goal=meets_raw,
                raw_reasons=raw_reasons,
                splits_validated=splits_ok,
                is_robust=is_robust,
            )
        )
    return views


def select_best_robust(views: list[CandidateGoalView]) -> CandidateGoalView | None:
    robust = [view for view in views if view.is_robust]
    if not robust:
        return None
    return max(robust, key=lambda view: (view.return_pct or 0.0, view.profit_factor or 0.0))


def select_closest_raw(views: list[CandidateGoalView]) -> CandidateGoalView | None:
    if not views:
        return None
    return max(views, key=lambda view: (view.return_pct or float("-inf"), view.profit_factor or 0.0))


def _run_full_period_tasks(task_paths: list[Path], *, allow_gui_clicks: bool, timeout_seconds: int) -> tuple[int, bool]:
    """Run a list of generated task files. Returns (count_run, halted)."""

    run_count = 0
    for task_path in task_paths:
        result = execute_run_task(
            str(task_path),
            allow_gui_clicks=allow_gui_clicks,
            timeout_seconds=timeout_seconds,
            execution_mode="cli",
        )
        run_count += 1
        update_leaderboard_csv()
        update_summary_md()
        if result.safety_ui_failure:
            return run_count, True
    return run_count, False


def _materialize_planned_tasks(experiment_path: Path, slug: str) -> list[Path]:
    """Expand a planner experiment JSON into concrete task files on disk."""

    payload = load_planned_experiment(experiment_path)
    from mt5_research_agent.experiment import generated_tasks_dir
    from mt5_research_agent.task import load_task

    base_task = load_task(payload["base_task"])
    tasks_dir = generated_tasks_dir() / str(payload["name"])
    tasks_dir.mkdir(parents=True, exist_ok=True)
    paths: list[Path] = []
    for index, combo in enumerate(payload["tasks"], start=1):
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
            "inputs": {**base_task.inputs, **{str(k): str(v) for k, v in combo.items()}},
            "acceptance": {
                "min_profit": base_task.acceptance.min_profit,
                "min_profit_factor": base_task.acceptance.min_profit_factor,
                "max_equity_dd_pct": base_task.acceptance.max_equity_dd_pct,
                "min_trades": base_task.acceptance.min_trades,
            },
        }
        path = tasks_dir / f"{task_payload['test_id']}.json"
        path.write_text(json.dumps(task_payload, indent=2), encoding="utf-8")
        paths.append(path)
    return paths


def run_goal_seek(
    request_path: str,
    *,
    max_rounds: int = 3,
    allow_gui_clicks: bool = False,
    timeout_seconds: int = 1800,
) -> GoalSeekResult:
    request = parse_research_request(request_path)
    if request.todos:
        raise ValueError("Research request is ambiguous. Resolve TODOs with plan-from-request first.")
    goal = goal_from_request(request)

    artifacts = write_research_plan(request)
    if artifacts.task_path is None or request.split_acceptance is None:
        raise ValueError("Request must be fully specified (base task + split acceptance) for goal seeking.")

    split_experiment = SplitExperiment(
        name=f"{request.slug}_split_validation",
        base_task=str(artifacts.task_path),
        splits=request.splits,
        acceptance=request.split_acceptance,
    )

    started_at = time.monotonic()
    tests_run = 0
    rounds = 0
    stop_reason = ""

    # Round 1: the bounded baseline sweep from the request parameter space.
    experiment_payload = build_experiment_payload(request, artifacts.task_path)
    experiment = ExperimentSpec(
        name=str(experiment_payload["name"]),
        base_task=str(experiment_payload["base_task"]),
        matrix=dict(experiment_payload["matrix"]),
        limits=ExperimentLimits(
            max_tests=min(int(experiment_payload["limits"]["max_tests"]), goal.max_tests),
            stop_after_failures=int(experiment_payload["limits"]["stop_after_failures"]),
        ),
        id_prefix=str(experiment_payload.get("id_prefix") or ""),
    )
    base_task = validate_task_payload(build_task_payload(request))
    generated = build_generated_tasks(experiment, base_task)
    task_paths = write_generated_tasks(experiment, generated)

    halted = False
    while rounds < max_rounds and tests_run < goal.max_tests and task_paths:
        rounds += 1
        # Respect the remaining budget.
        remaining = goal.max_tests - tests_run
        batch = task_paths[:remaining]
        run_count, halted = _run_full_period_tasks(
            batch, allow_gui_clicks=allow_gui_clicks, timeout_seconds=timeout_seconds
        )
        tests_run += run_count
        if halted:
            stop_reason = "safety/UI failure"
            break

        # Split-validate the strongest raw candidates this round.
        views = build_candidate_views(request, goal)
        top = sorted(
            (v for v in views if v.splits_validated is None and v.meets_raw_goal),
            key=lambda v: (v.return_pct or 0.0, v.profit_factor or 0.0),
            reverse=True,
        )[: max(1, request.top_candidates_for_splits)]
        for view in top:
            candidate_payload = build_task_payload(request)
            candidate_payload["test_id"] = view.test_id
            candidate_payload["name"] = view.task_name or request.slug
            candidate_payload["inputs"] = view.inputs or request.baseline_inputs
            candidate_task = validate_task_payload(candidate_payload)
            try:
                run_split_validation_for_candidate(
                    split_experiment,
                    candidate_task,
                    view.test_id,
                    allow_gui_clicks=allow_gui_clicks,
                    timeout_seconds=timeout_seconds,
                )
            except Exception:
                # A split failure is preserved; keep searching with the budget.
                break

        views = build_candidate_views(request, goal)
        if select_best_robust(views) is not None:
            stop_reason = "target robustly reached"
            break

        if (time.monotonic() - started_at) / 60.0 >= (goal.max_runtime_minutes or float("inf")):
            stop_reason = "runtime budget exhausted"
            break

        if tests_run >= goal.max_tests:
            stop_reason = "test budget exhausted"
            break

        # Refine: ask the planner for nearby untested combinations.
        try:
            _, experiment_path = build_next_plan(request)
            task_paths = _materialize_planned_tasks(experiment_path, request.slug)
        except Exception:
            task_paths = []
        if not task_paths:
            stop_reason = "no new untested combinations (progress stalled)"
            break

    if not stop_reason:
        stop_reason = "max rounds reached" if rounds >= max_rounds else "test budget exhausted"

    views = build_candidate_views(request, goal)
    best_robust = select_best_robust(views)
    closest_raw = select_closest_raw(views)
    report_path = write_goal_report(request, goal, views, best_robust, closest_raw, stop_reason, tests_run, rounds)

    return GoalSeekResult(
        slug=request.slug,
        target_reached=best_robust is not None,
        best_robust_id=best_robust.test_id if best_robust else "",
        closest_raw_id=closest_raw.test_id if closest_raw else "",
        tests_run=tests_run,
        rounds=rounds,
        stop_reason=stop_reason,
        report_path=str(report_path),
        candidates=views,
    )


def goal_report_path(slug: str) -> Path:
    return get_results_dir() / f"final_report_{slug}.md"


def _format_candidate(view: CandidateGoalView | None) -> str:
    if view is None:
        return "none"
    return (
        f"`{view.test_id}` return={view.return_pct}% pf={view.profit_factor} "
        f"dd={view.drawdown_pct}% trades={view.total_trades} "
        f"splits_validated={view.splits_validated}"
    )


def write_goal_report(
    request: ParsedResearchRequest,
    goal: ResearchGoal,
    views: list[CandidateGoalView],
    best_robust: CandidateGoalView | None,
    closest_raw: CandidateGoalView | None,
    stop_reason: str,
    tests_run: int,
    rounds: int,
) -> Path:
    output_path = goal_report_path(request.slug)
    lines = [
        f"# Final Goal Report: {request.slug}",
        "",
        f"- Generated at: {datetime.now(timezone.utc).isoformat()}",
        f"- Tests run: {tests_run}",
        f"- Rounds: {rounds}",
        f"- Stop reason: {stop_reason}",
        "",
        "## Goal",
        "",
        f"- Target total return %: {goal.target_total_return_pct}",
        f"- Target period years: {goal.target_period_years}",
        f"- Max equity drawdown %: {goal.max_equity_drawdown_pct}",
        f"- Min profit factor: {goal.min_profit_factor}",
        f"- Min trades: {goal.min_trades}",
        f"- Must validate splits: {goal.must_validate_splits}",
        f"- Objective: {goal.objective}",
        "",
        "## Outcome",
        "",
    ]

    if best_robust is not None:
        lines.append("Target robustly reached.")
        lines.append("")
        lines.append(f"Best robust candidate: {_format_candidate(best_robust)}")
        lines.append(f"Closest raw candidate: {_format_candidate(closest_raw)}")
    else:
        lines.append("Target not robustly reached.")
        lines.append("")
        lines.append("Best robust candidate: none")
        lines.append(f"Closest raw candidate: {_format_candidate(closest_raw)}")
        if closest_raw is not None:
            reasons = closest_raw.raw_reasons or []
            if closest_raw.meets_raw_goal and closest_raw.splits_validated is False:
                reasons = ["SPLITS_FAILED"]
            elif closest_raw.meets_raw_goal and closest_raw.splits_validated is None:
                reasons = ["SPLITS_NOT_VALIDATED"]
            lines.append(f"Rejected because: {', '.join(reasons) or 'unknown'}")
        next_direction = (
            "Widen or shift the parameter ranges that hit drawdown limits, "
            "and re-run split validation on the closest raw candidate."
        )
        lines.append(f"Next suggested research direction: {next_direction}")

    lines.extend(["", "## All Candidates", ""])
    lines.append("| Test ID | Return % | PF | DD % | Trades | Meets Raw Goal | Splits | Robust | Raw Reasons |")
    lines.append("| --- | --- | --- | --- | --- | --- | --- | --- | --- |")
    for view in sorted(views, key=lambda v: (v.return_pct or float("-inf")), reverse=True):
        lines.append(
            f"| {view.test_id} | {view.return_pct} | {view.profit_factor} | {view.drawdown_pct} | "
            f"{view.total_trades} | {'yes' if view.meets_raw_goal else 'no'} | {view.splits_validated} | "
            f"{'yes' if view.is_robust else 'no'} | {', '.join(view.raw_reasons) or '-'} |"
        )
    if not views:
        lines.append("| (no runs stored) | - | - | - | - | - | - | - | - |")

    lines.extend(
        [
            "",
            "## Safety Note",
            "",
            "This report describes Strategy Tester backtests only. It is not a "
            "prediction of future results and makes no guarantee of profitability. "
            "All runs, including failures, are preserved in the result store.",
        ]
    )
    output_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return output_path


def run_goal_seek_command(
    request_path: str,
    *,
    max_rounds: int,
    allow_gui_clicks: bool,
    timeout_seconds: int,
) -> int:
    try:
        result = run_goal_seek(
            request_path,
            max_rounds=max_rounds,
            allow_gui_clicks=allow_gui_clicks,
            timeout_seconds=timeout_seconds,
        )
    except Exception as exc:
        print(str(exc))
        return 1

    print(f"slug: {result.slug}")
    print(f"target reached: {result.target_reached}")
    print(f"tests run: {result.tests_run}")
    print(f"rounds: {result.rounds}")
    print(f"stop reason: {result.stop_reason}")
    if result.best_robust_id:
        print(f"best robust candidate: {result.best_robust_id}")
    if result.closest_raw_id:
        print(f"closest raw candidate: {result.closest_raw_id}")
    print(f"final report: {result.report_path}")
    return 0


def run_final_report_command(request_path: str) -> int:
    try:
        request = parse_research_request(request_path)
    except Exception as exc:
        print(str(exc))
        return 1
    goal = goal_from_request(request)
    views = build_candidate_views(request, goal)
    best_robust = select_best_robust(views)
    closest_raw = select_closest_raw(views)
    report_path = write_goal_report(
        request, goal, views, best_robust, closest_raw, "report-only (no new runs)", tests_run=0, rounds=0
    )
    print(f"target reached: {best_robust is not None}")
    if best_robust is not None:
        print(f"best robust candidate: {best_robust.test_id}")
    if closest_raw is not None:
        print(f"closest raw candidate: {closest_raw.test_id}")
    print(f"final report: {report_path}")
    return 0
