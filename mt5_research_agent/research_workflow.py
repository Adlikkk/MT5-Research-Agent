from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from mt5_research_agent.background_runner import task_id_prefix, write_generated_task
from mt5_research_agent.config import load_config
from mt5_research_agent.goal import ResearchGoal, describe_goal, parse_goal_section
from mt5_research_agent.report_parser import metrics_drawdown_pct
from mt5_research_agent.experiment import (
    ExperimentLimits,
    ExperimentSpec,
    build_generated_tasks,
    load_experiment_state,
    save_experiment_state,
    write_generated_tasks,
)
from mt5_research_agent.result_store import fetch_run, fetch_runs, get_results_dir, update_leaderboard_csv, update_summary_md
from mt5_research_agent.result_store import RunAttempt, make_attempt_id, store_run_attempt
from mt5_research_agent.run_task import execute_run_task
from mt5_research_agent.split_validation import (
    SplitAcceptance,
    SplitExperiment,
    SplitWindow,
    build_split_tasks,
    evaluate_split_row,
    split_validation_report_path,
    summarize_candidate,
    update_candidate_split_result,
    write_split_tasks,
    write_split_validation_report,
)
from mt5_research_agent.task import ResearchTask, validate_task_payload


SECTION_NAMES = {
    "goal",
    "goal constraints",
    "ea",
    "symbol",
    "timeframe",
    "date range",
    "baseline inputs",
    "parameters allowed to change",
    "hard limits",
    "splits required",
    "stress tests required",
    "ranking rules",
    "stop rules",
}


@dataclass(slots=True)
class ParsedResearchRequest:
    slug: str
    source_path: str
    original_markdown: str
    goal: str
    ea: str
    symbol: str
    timeframe: str
    period_from: str
    period_to: str
    baseline_inputs: dict[str, str]
    parameter_space: dict[str, list[str]]
    acceptance_payload: dict[str, Any]
    experiment_limits: dict[str, int]
    splits: list[SplitWindow]
    split_acceptance: SplitAcceptance | None
    top_candidates_for_splits: int
    stress_tests_required: list[str]
    ranking_rules: list[str]
    stop_rules: list[str]
    todos: list[str]
    goal_constraints: ResearchGoal | None = None


@dataclass(slots=True)
class ResearchPlanArtifacts:
    plan_dir: Path
    task_path: Path | None
    experiment_path: Path | None
    split_experiment_path: Path | None
    todo_path: Path | None
    generated_task_paths: list[Path]


def slugify(text: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "_", text.casefold()).strip("_")
    return slug or "research_request"


def research_plan_dir(slug: str) -> Path:
    config = load_config()
    path = Path(config.artifacts_dir).resolve() / "research_plans" / slug
    path.mkdir(parents=True, exist_ok=True)
    return path


def research_report_path(slug: str) -> Path:
    return get_results_dir() / f"research_{slug}.md"


def planner_history_for_slug(slug: str) -> list[dict[str, str]]:
    config = load_config()
    history_dir = Path(config.artifacts_dir).resolve() / "plans"
    history: list[dict[str, str]] = []
    if not history_dir.exists():
        return history
    for path in sorted(history_dir.glob("plan_*.md")):
        try:
            text = path.read_text(encoding="utf-8")
        except OSError:
            continue
        request_line = next((line for line in text.splitlines() if line.startswith("- Request slug: ")), "")
        experiment_line = next((line for line in text.splitlines() if line.startswith("- Generated experiment: ")), "")
        if request_line.removeprefix("- Request slug: ").strip() != slug:
            continue
        history.append(
            {
                "plan_path": str(path),
                "experiment_path": experiment_line.removeprefix("- Generated experiment: ").strip(),
            }
        )
    return history


def parse_request_sections(markdown_text: str) -> dict[str, str]:
    sections: dict[str, list[str]] = {}
    current: str | None = None
    for raw_line in markdown_text.splitlines():
        line = raw_line.rstrip()
        heading_match = re.match(r"^\s{0,3}#{1,6}\s+(.*)$", line)
        if heading_match:
            heading = heading_match.group(1).strip().casefold()
            current = heading if heading in SECTION_NAMES else None
            if current is not None:
                sections.setdefault(current, [])
            continue
        if current is not None:
            sections[current].append(line)
    return {key: "\n".join(value).strip() for key, value in sections.items()}


def parse_single_value(section_text: str) -> str:
    lines = [line.strip() for line in section_text.splitlines() if line.strip()]
    if not lines:
        return ""
    if len(lines) == 1:
        return lines[0].removeprefix("-").strip()
    return " ".join(line.removeprefix("-").strip() for line in lines)


def parse_bullet_items(section_text: str) -> list[str]:
    items: list[str] = []
    for raw_line in section_text.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        if line.startswith(("-", "*")):
            items.append(line[1:].strip())
        else:
            items.append(line)
    return items


def parse_key_value_items(section_text: str) -> dict[str, str]:
    items: dict[str, str] = {}
    for item in parse_bullet_items(section_text):
        if ":" not in item:
            continue
        key, value = item.split(":", 1)
        items[key.strip()] = value.strip()
    return items


def parse_date_range(section_text: str) -> tuple[str, str]:
    value = parse_single_value(section_text)
    match = re.match(r"^(\d{4}\.\d{2}\.\d{2})\s*(?:->|to|-)\s*(\d{4}\.\d{2}\.\d{2})$", value)
    if not match:
        return "", ""
    return match.group(1), match.group(2)


def parse_parameter_values(text: str) -> list[str]:
    value = text.strip()
    if value.startswith("[") and value.endswith("]"):
        value = value[1:-1]
    parts = [part.strip().strip('"').strip("'") for part in value.split(",")]
    return [part for part in parts if part]


def parse_splits_section(section_text: str) -> tuple[list[SplitWindow], dict[str, str]]:
    splits: list[SplitWindow] = []
    meta: dict[str, str] = {}
    for item in parse_bullet_items(section_text):
        if ":" not in item:
            continue
        key, value = item.split(":", 1)
        key = key.strip()
        value = value.strip()
        range_match = re.match(r"^(\d{4}\.\d{2}\.\d{2})\s*(?:->|to|-)\s*(\d{4}\.\d{2}\.\d{2})$", value)
        if range_match:
            splits.append(
                SplitWindow(
                    label=key,
                    period_from=range_match.group(1),
                    period_to=range_match.group(2),
                )
            )
            continue
        meta[key] = value
    return splits, meta


def parse_research_request(request_path: str | Path) -> ParsedResearchRequest:
    path = Path(request_path)
    markdown_text = path.read_text(encoding="utf-8")
    sections = parse_request_sections(markdown_text)
    todos: list[str] = []

    goal = parse_single_value(sections.get("goal", ""))
    ea = parse_single_value(sections.get("ea", ""))
    symbol = parse_single_value(sections.get("symbol", ""))
    timeframe = parse_single_value(sections.get("timeframe", ""))
    period_from, period_to = parse_date_range(sections.get("date range", ""))
    baseline_inputs = parse_key_value_items(sections.get("baseline inputs", ""))

    parameter_space: dict[str, list[str]] = {}
    for key, value in parse_key_value_items(sections.get("parameters allowed to change", "")).items():
        values = parse_parameter_values(value)
        if values:
            parameter_space[key] = values

    hard_limits = parse_key_value_items(sections.get("hard limits", ""))
    stop_rules = parse_bullet_items(sections.get("stop rules", ""))
    stop_rule_map = parse_key_value_items(sections.get("stop rules", ""))
    ranking_rules = parse_bullet_items(sections.get("ranking rules", ""))
    stress_tests_required = parse_bullet_items(sections.get("stress tests required", ""))
    splits, split_meta = parse_splits_section(sections.get("splits required", ""))

    goal_constraints: ResearchGoal | None = None
    goal_items = parse_key_value_items(sections.get("goal constraints", ""))
    if goal_items:
        try:
            goal_constraints = parse_goal_section(goal_items)
        except ValueError as exc:
            todos.append(f"Goal constraints invalid: {exc}")

    for field_name, value in (
        ("Goal", goal),
        ("EA", ea),
        ("Symbol", symbol),
        ("Timeframe", timeframe),
    ):
        if not value:
            todos.append(f"Missing {field_name} section value.")

    if not period_from or not period_to:
        todos.append("Date range must use `YYYY.MM.DD -> YYYY.MM.DD`.")
    if not baseline_inputs:
        todos.append("Baseline inputs are required.")
    if not parameter_space:
        todos.append("Parameters allowed to change must include at least one key with a list of values.")

    acceptance_payload: dict[str, Any] = {}
    for key, converter in (
        ("min_profit", float),
        ("min_profit_factor", float),
        ("max_equity_dd_pct", float),
        ("min_trades", int),
    ):
        raw_value = hard_limits.get(key)
        if raw_value is None:
            todos.append(f"Hard limits must define `{key}`.")
            continue
        acceptance_payload[key] = converter(raw_value)

    experiment_limits: dict[str, int] = {}
    for key in ("max_tests", "stop_after_failures"):
        raw_value = hard_limits.get(key, stop_rule_map.get(key))
        if raw_value is None:
            todos.append(f"Need `{key}` in Hard limits or Stop rules.")
            continue
        experiment_limits[key] = int(raw_value)

    if not splits:
        todos.append("Splits required must define at least one labeled split range.")

    top_candidates_for_splits = 1
    raw_top_candidates = split_meta.get("top_candidates")
    if raw_top_candidates is not None:
        top_candidates_for_splits = int(raw_top_candidates)
    else:
        todos.append("Splits required should define `top_candidates:` to avoid guessing how many candidates to validate.")

    split_acceptance: SplitAcceptance | None = None
    split_acceptance_values = {
        "all_splits_profitable": split_meta.get("all_splits_profitable"),
        "min_profit_factor_each_split": split_meta.get("min_profit_factor_each_split"),
        "max_equity_dd_pct_each_split": split_meta.get("max_equity_dd_pct_each_split"),
        "min_trades_each_split": split_meta.get("min_trades_each_split"),
    }
    if all(value is not None for value in split_acceptance_values.values()):
        profitable_value = split_acceptance_values["all_splits_profitable"]
        min_pf_value = split_acceptance_values["min_profit_factor_each_split"]
        max_dd_value = split_acceptance_values["max_equity_dd_pct_each_split"]
        min_trades_value = split_acceptance_values["min_trades_each_split"]
        assert profitable_value is not None
        assert min_pf_value is not None
        assert max_dd_value is not None
        assert min_trades_value is not None
        split_acceptance = SplitAcceptance(
            all_splits_profitable=profitable_value.casefold() == "true",
            min_profit_factor_each_split=float(min_pf_value),
            max_equity_dd_pct_each_split=float(max_dd_value),
            min_trades_each_split=int(min_trades_value),
        )
    else:
        todos.append("Splits required must define split acceptance thresholds.")

    return ParsedResearchRequest(
        slug=slugify(path.stem),
        source_path=str(path),
        original_markdown=markdown_text,
        goal=goal,
        ea=ea,
        symbol=symbol,
        timeframe=timeframe,
        period_from=period_from,
        period_to=period_to,
        baseline_inputs=baseline_inputs,
        parameter_space=parameter_space,
        acceptance_payload=acceptance_payload,
        experiment_limits=experiment_limits,
        splits=splits,
        split_acceptance=split_acceptance,
        top_candidates_for_splits=top_candidates_for_splits,
        stress_tests_required=stress_tests_required,
        ranking_rules=ranking_rules,
        stop_rules=stop_rules,
        todos=todos,
        goal_constraints=goal_constraints,
    )


def build_task_payload(request: ParsedResearchRequest) -> dict[str, Any]:
    return {
        "name": request.slug,
        "ea": request.ea,
        "symbol": request.symbol,
        "timeframe": request.timeframe,
        "period_from": request.period_from,
        "period_to": request.period_to,
        "deposit": 10000,
        "model": "Every tick based on real ticks",
        "inputs": request.baseline_inputs,
        "acceptance": request.acceptance_payload,
    }


def build_experiment_payload(request: ParsedResearchRequest, task_path: Path) -> dict[str, Any]:
    return {
        "name": request.slug,
        "base_task": str(task_path),
        "matrix": request.parameter_space,
        "limits": request.experiment_limits,
        "id_prefix": task_id_prefix(validate_task_payload(build_task_payload(request))),
    }


def build_split_experiment_payload(request: ParsedResearchRequest, task_path: Path) -> dict[str, Any]:
    if request.split_acceptance is None:
        raise ValueError("Split acceptance must be available before building split experiment payload.")
    return {
        "name": f"{request.slug}_split_validation",
        "base_task": str(task_path),
        "splits": [
            {"label": split.label, "from": split.period_from, "to": split.period_to}
            for split in request.splits
        ],
        "acceptance": {
            "all_splits_profitable": request.split_acceptance.all_splits_profitable,
            "min_profit_factor_each_split": request.split_acceptance.min_profit_factor_each_split,
            "max_equity_dd_pct_each_split": request.split_acceptance.max_equity_dd_pct_each_split,
            "min_trades_each_split": request.split_acceptance.min_trades_each_split,
        },
    }


def write_research_plan(request: ParsedResearchRequest) -> ResearchPlanArtifacts:
    plan_dir = research_plan_dir(request.slug)
    todo_path: Path | None = None
    generated_task_paths: list[Path] = []

    if request.todos:
        todo_path = plan_dir / "TODO.md"
        todo_lines = ["# Research Request TODOs", ""]
        todo_lines.extend(f"- {item}" for item in request.todos)
        todo_path.write_text("\n".join(todo_lines) + "\n", encoding="utf-8")

    task_path: Path | None = None
    experiment_path: Path | None = None
    split_experiment_path: Path | None = None

    if not request.todos:
        task_payload = build_task_payload(request)
        validate_task_payload(task_payload)
        task_path = plan_dir / "base_task.json"
        task_path.write_text(json.dumps(task_payload, indent=2), encoding="utf-8")

        experiment_payload = build_experiment_payload(request, task_path)
        experiment_path = plan_dir / "experiment.json"
        experiment_path.write_text(json.dumps(experiment_payload, indent=2), encoding="utf-8")
        experiment = ExperimentSpec(
            name=str(experiment_payload["name"]),
            base_task=str(experiment_payload["base_task"]),
            matrix=dict(experiment_payload["matrix"]),
            limits=ExperimentLimits(
                max_tests=int(experiment_payload["limits"]["max_tests"]),
                stop_after_failures=int(experiment_payload["limits"]["stop_after_failures"]),
            ),
            id_prefix=str(experiment_payload["id_prefix"]),
        )
        generated_tasks = build_generated_tasks(experiment, validate_task_payload(task_payload))
        generated_task_paths = [write_generated_task(task_payload_item) for task_payload_item in generated_tasks]
        for generated_task_payload in generated_tasks:
            store_run_attempt(
                RunAttempt(
                    attempt_id=make_attempt_id(str(generated_task_payload["test_id"]), "PLANNED"),
                    test_id=str(generated_task_payload["test_id"]),
                    run_status="PLANNED",
                    execution_mode="cli",
                    run_kind="full_period",
                    parent_candidate_id="",
                    split_id="",
                    task_name=str(generated_task_payload["name"]),
                    raw_report_path="",
                    parsed_report_path="",
                    log_path="",
                    set_path="",
                    ini_path="",
                    command_line="",
                    expected_report_path="",
                    discovered_report_path="",
                    process_id=None,
                    process_exit_code=None,
                    process_started_at="",
                    process_ended_at="",
                    duration_seconds=None,
                    error="",
                    created_at=datetime.now(timezone.utc).isoformat(),
                )
            )

        split_experiment_payload = build_split_experiment_payload(request, task_path)
        split_experiment_path = plan_dir / "split_experiment.json"
        split_experiment_path.write_text(json.dumps(split_experiment_payload, indent=2), encoding="utf-8")

    return ResearchPlanArtifacts(
        plan_dir=plan_dir,
        task_path=task_path,
        experiment_path=experiment_path,
        split_experiment_path=split_experiment_path,
        todo_path=todo_path,
        generated_task_paths=generated_task_paths,
    )


def choose_top_candidate_rows(experiment_name: str, limit: int) -> list[dict[str, Any]]:
    rows = []
    for row in fetch_runs():
        if row.get("run_kind") != "full_period":
            continue
        if not str(row.get("task_name", "")).startswith(experiment_name):
            continue
        rows.append(row)

    def sort_key(row: dict[str, Any]) -> tuple[Any, ...]:
        metrics = json.loads(row["parsed_metrics_json"])
        return (
            int(row["pass_fail"]),
            metrics.get("profit_factor") or 0,
            metrics.get("net_profit") or 0,
        )

    rows.sort(key=sort_key, reverse=True)
    return rows[:limit]


def run_split_validation_for_candidate(
    split_experiment: SplitExperiment,
    candidate_task: ResearchTask,
    candidate_id: str,
    *,
    allow_gui_clicks: bool,
    timeout_seconds: int,
    execution_mode: str = "cli",
) -> bool:
    tasks = build_split_tasks(split_experiment, candidate_task, candidate_id)
    task_paths = write_split_tasks(split_experiment, candidate_id, tasks)

    for index, task_path in enumerate(task_paths, start=1):
        result = execute_run_task(
            str(task_path),
            allow_gui_clicks=allow_gui_clicks,
            timeout_seconds=timeout_seconds,
            execution_mode=execution_mode,
            run_kind="split",
            parent_candidate_id=candidate_id,
            split_id=split_experiment.splits[index - 1].label,
        )
        if result.safety_ui_failure:
            raise RuntimeError(f"Split validation stopped on safety/UI failure for {tasks[index - 1]['test_id']}.")

    rows = [
        row
        for row in fetch_runs()
        if row.get("parent_candidate_id") == candidate_id and row.get("run_kind") == "split"
    ]
    for row in rows:
        if row["rejection_reason"] == "REPORT_MISSING":
            continue
        passed, reasons = evaluate_split_row(row, split_experiment.acceptance)
        update_candidate_split_result(row["test_id"], passed, ";".join(reasons))
    rows = [
        row
        for row in fetch_runs()
        if row.get("parent_candidate_id") == candidate_id and row.get("run_kind") == "split"
    ]
    final_passed = bool(rows) and all(row["pass_fail"] for row in rows)
    write_split_validation_report(split_experiment, candidate_id, rows, final_passed)
    update_leaderboard_csv()
    update_summary_md()
    return final_passed


def render_runs_table(rows: list[dict[str, Any]]) -> list[str]:
    lines = [
        "| Test ID | Kind | Parent | Split | Pass/Fail | Net Profit | PF | DD % | Trades | Reason |",
        "| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |",
    ]
    for row in rows:
        metrics = json.loads(row["parsed_metrics_json"])
        lines.append(
            f"| {row['test_id']} | {row['run_kind']} | {row['parent_candidate_id'] or '-'} | {row['split_id'] or '-'} | "
            f"{'PASS' if row['pass_fail'] else 'FAIL'} | {metrics.get('net_profit')} | {metrics.get('profit_factor')} | "
            f"{metrics_drawdown_pct(metrics)} | {metrics.get('total_trades')} | {row['rejection_reason'] or '-'} |"
        )
    return lines


def write_research_report(
    request: ParsedResearchRequest,
    experiment_name: str,
    candidate_ids: list[str],
    limitations: list[str],
) -> Path:
    rows = [
        row for row in fetch_runs()
        if str(row.get("task_name", "")).startswith(experiment_name)
        or row.get("parent_candidate_id") in candidate_ids
        or row.get("test_id") in candidate_ids
    ]
    rows.sort(key=lambda row: (row["run_kind"], row["test_id"]))
    full_rows = [row for row in rows if row.get("run_kind") == "full_period"]
    rejected_rows = [row for row in rows if not row["pass_fail"]]

    best_candidate_line = "No robust candidate found."
    robust_candidates: list[str] = []
    for candidate_id in candidate_ids:
        split_rows = [row for row in rows if row.get("parent_candidate_id") == candidate_id and row.get("run_kind") == "split"]
        full_row = next((row for row in full_rows if row["test_id"] == candidate_id), None)
        if full_row is None:
            continue
        if split_rows and all(row["pass_fail"] for row in split_rows):
            robust_candidates.append(candidate_id)
    if robust_candidates:
        selected = max(
            robust_candidates,
            key=lambda candidate_id: json.loads(
                next(row for row in full_rows if row["test_id"] == candidate_id)["parsed_metrics_json"]
            ).get("profit_factor") or 0,
        )
        best_candidate_line = f"Best candidate: `{selected}`"

    every_test_lines = render_runs_table(rows) if rows else ["No runs stored for this research request."]
    rejected_lines = render_runs_table(rejected_rows) if rejected_rows else ["No rejected candidates."]
    ranking_lines = [f"- {rule}" for rule in request.ranking_rules] or ["- No ranking rules supplied."]
    stress_lines = [f"- Stress test requested but not automated in this phase: {item}" for item in request.stress_tests_required]
    limitation_lines = [f"- {item}" for item in limitations] or ["- No extra limitations recorded."]
    planner_history = planner_history_for_slug(request.slug)

    report_path = research_report_path(request.slug)
    lines = [
        f"# Research {request.slug}",
        "",
        "## Original Request",
        "",
        "```markdown",
        request.original_markdown.rstrip(),
        "```",
        "",
        "## Tested Parameter Space",
        "",
        f"- Baseline inputs: {json.dumps(request.baseline_inputs, sort_keys=True)}",
        f"- Variable inputs: {json.dumps(request.parameter_space, sort_keys=True)}",
        f"- Split candidates checked: {candidate_ids or ['none']}",
        "",
        "## Every Test Row",
        "",
        *every_test_lines,
        "",
        "## Rejected Candidates",
        "",
        *rejected_lines,
        "",
        "## Best Candidate",
        "",
        best_candidate_line,
        "",
        "## Robustness Notes",
        "",
        *ranking_lines,
        *stress_lines,
        "",
        "## Limitations",
        "",
        *limitation_lines,
        "",
        "## Planner History",
        "",
    ]
    if planner_history:
        lines.append("| Plan | Experiment |")
        lines.append("| --- | --- |")
        for item in planner_history:
            lines.append(f"| {item['plan_path']} | {item['experiment_path'] or '-'} |")
    else:
        lines.append("No planner history yet.")
    report_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return report_path


RESEARCH_REQUEST_TEMPLATE = """# {title}

## Goal
{goal}

## Goal constraints
- target_total_return_pct: 250
- target_period_years: 5
- max_equity_drawdown_pct: 25
- min_profit_factor: 1.2
- min_trades: 250
- must_validate_splits: true
- max_tests: 50
- max_runtime_minutes: 360
- objective: maximize robust return under drawdown and validation constraints

## EA
{ea}

## Symbol
{symbol}

## Timeframe
{timeframe}

## Date range
{period_from} -> {period_to}

## Baseline inputs
- TODO_input: value

## Parameters allowed to change
- TODO_input: [value_a, value_b]

## Hard limits
- min_profit: 0
- min_profit_factor: 1.2
- max_equity_dd_pct: 25
- min_trades: 250
- max_tests: 50
- stop_after_failures: 10

## Splits required
- top_candidates: 2
- S1: {period_from} -> {period_to}
- all_splits_profitable: true
- min_profit_factor_each_split: 1.1
- max_equity_dd_pct_each_split: 28
- min_trades_each_split: 60

## Stress tests required
- Weekend gap stress is still manual in this phase.

## Ranking rules
- all splits profitable
- PF stability
- max equity drawdown
- enough trades

## Stop rules
- stop_after_failures: 10
- stop_on_ui_failure: true
"""


def research_requests_dir() -> Path:
    path = Path("research_requests")
    path.mkdir(parents=True, exist_ok=True)
    return path


def scaffold_research_request(prompt_path: str | Path) -> Path:
    """Turn a free-text prompt markdown file into a structured request scaffold.

    This is deterministic and local-only: it embeds the original prompt as the
    Goal and fills the canonical section headings with TODO placeholders so the
    user (or an optional AI provider) can complete it. It never invents EA,
    symbol, or parameter values.
    """

    source = Path(prompt_path)
    prompt_text = source.read_text(encoding="utf-8").strip() if source.exists() else str(prompt_path).strip()
    title = source.stem.replace("_", " ").title() if source.exists() else "Research Request"
    content = RESEARCH_REQUEST_TEMPLATE.format(
        title=title,
        goal=prompt_text or "Describe the research goal here.",
        ea="TODO_EA_NAME",
        symbol="TODO_SYMBOL",
        timeframe="TODO_TIMEFRAME",
        period_from="2020.01.01",
        period_to="2025.01.01",
    )
    slug = slugify(source.stem if source.exists() else "research_request")
    output_path = research_requests_dir() / f"{slug}.md"
    output_path.write_text(content, encoding="utf-8")
    return output_path


def run_create_research_request_command(prompt_path: str) -> int:
    try:
        output_path = scaffold_research_request(prompt_path)
    except Exception as exc:
        print(str(exc))
        return 1
    print(f"research request scaffold: {output_path}")
    print("review TODO placeholders, then run validate-research-request")
    return 0


def run_validate_research_request_command(request_path: str) -> int:
    try:
        request = parse_research_request(request_path)
    except Exception as exc:
        print(str(exc))
        return 1

    print(f"slug: {request.slug}")
    print(f"ea: {request.ea or '<missing>'}")
    print(f"symbol: {request.symbol or '<missing>'}")
    print(f"timeframe: {request.timeframe or '<missing>'}")
    print(f"date range: {request.period_from or '<missing>'} -> {request.period_to or '<missing>'}")
    print(f"parameter keys: {', '.join(request.parameter_space) or '<none>'}")
    print(f"splits: {len(request.splits)}")
    if request.goal_constraints is not None:
        print("goal constraints:")
        for line in describe_goal(request.goal_constraints):
            print(f"  {line}")
    else:
        print("goal constraints: <none>")
    if request.todos:
        print("validation: needs work")
        for item in request.todos:
            print(f"- {item}")
        return 1
    print("validation: ok")
    return 0


def run_split_validate_command(
    candidate_id: str,
    request_path: str,
    *,
    allow_gui_clicks: bool = False,
    timeout_seconds: int = 1800,
) -> int:
    """Run split validation for an already-tested candidate (by test_id).

    Splits and split-acceptance thresholds come from the supplied research
    request; the candidate's tested input values come from its stored run.
    """

    try:
        request = parse_research_request(request_path)
    except Exception as exc:
        print(str(exc))
        return 1
    if request.todos:
        print("request is ambiguous; resolve TODOs before split validation.")
        for item in request.todos:
            print(f"- {item}")
        return 1
    if request.split_acceptance is None:
        print("request has no split acceptance thresholds.")
        return 1

    row = fetch_run(candidate_id)
    if row is None:
        print(f"No stored run found for candidate: {candidate_id}")
        return 1

    artifacts = write_research_plan(request)
    if artifacts.task_path is None:
        print("Could not build a base task from the request.")
        return 1

    candidate_payload = build_task_payload(request)
    candidate_payload["test_id"] = candidate_id
    candidate_payload["name"] = row["task_name"]
    try:
        candidate_payload["inputs"] = json.loads(row["full_inputs_json"])
    except (TypeError, json.JSONDecodeError):
        candidate_payload["inputs"] = request.baseline_inputs
    candidate_task = validate_task_payload(candidate_payload)

    split_experiment = SplitExperiment(
        name=f"{request.slug}_split_validation",
        base_task=str(artifacts.task_path),
        splits=request.splits,
        acceptance=request.split_acceptance,
    )
    try:
        passed = run_split_validation_for_candidate(
            split_experiment,
            candidate_task,
            candidate_id,
            allow_gui_clicks=allow_gui_clicks,
            timeout_seconds=timeout_seconds,
        )
        summary_path = summarize_candidate(candidate_id)
    except Exception as exc:
        print(str(exc))
        return 1

    print(f"candidate_id: {candidate_id}")
    print(f"decision: {'PASS' if passed else 'FAIL'}")
    print(f"split report: {split_validation_report_path(split_experiment.name)}")
    print(f"candidate report: {summary_path}")
    return 0 if passed else 1


def run_candidate_report_command(candidate_id: str) -> int:
    try:
        path = summarize_candidate(candidate_id)
    except Exception as exc:
        print(str(exc))
        return 1
    print(f"candidate report: {path}")
    return 0


def run_plan_from_request_command(request_path: str) -> int:
    try:
        request = parse_research_request(request_path)
        artifacts = write_research_plan(request)
    except Exception as exc:
        print(str(exc))
        return 1

    print(f"plan dir: {artifacts.plan_dir}")
    if artifacts.task_path:
        print(f"base task: {artifacts.task_path}")
    if artifacts.experiment_path:
        print(f"experiment: {artifacts.experiment_path}")
    if artifacts.split_experiment_path:
        print(f"split experiment: {artifacts.split_experiment_path}")
    if artifacts.todo_path:
        print(f"todo: {artifacts.todo_path}")
    if artifacts.generated_task_paths:
        print(f"generated tasks: {len(artifacts.generated_task_paths)}")
        print(f"first generated task: {artifacts.generated_task_paths[0]}")
    if request.todos:
        print("plan contains TODOs; review before running research.")
    else:
        print("plan-from-request: ok")
    return 0


def run_research_command(
    request_path: str,
    allow_gui_clicks: bool,
    timeout_seconds: int = 1800,
    session: bool = False,
) -> int:
    execution_mode = "cli"
    if session:
        from mt5_research_agent.session import require_active_session_or_explain

        ok, message = require_active_session_or_explain(allow_gui_clicks=allow_gui_clicks)
        print(message)
        if not ok:
            return 2
        execution_mode = "gui"
        allow_gui_clicks = True

    try:
        request = parse_research_request(request_path)
        artifacts = write_research_plan(request)
    except Exception as exc:
        print(str(exc))
        return 1

    limitations: list[str] = []
    if request.todos:
        limitations.extend(request.todos)
        report_path = write_research_report(request, request.slug, [], limitations)
        print("request is ambiguous; review TODOs before running research.")
        print(f"report: {report_path}")
        return 1

    task_payload = build_task_payload(request)
    base_task = validate_task_payload(task_payload)
    if artifacts.task_path is None:
        raise RuntimeError("Expected a generated base task path for a fully specified research request.")
    experiment_payload = build_experiment_payload(request, artifacts.task_path)
    if request.split_acceptance is None:
        raise RuntimeError("Expected split acceptance for a fully specified research request.")
    experiment = ExperimentSpec(
        name=str(experiment_payload["name"]),
        base_task=str(experiment_payload["base_task"]),
        matrix=dict(experiment_payload["matrix"]),
        limits=ExperimentLimits(
            max_tests=int(experiment_payload["limits"]["max_tests"]),
            stop_after_failures=int(experiment_payload["limits"]["stop_after_failures"]),
        ),
    )
    split_experiment = SplitExperiment(
        name=f"{request.slug}_split_validation",
        base_task=str(artifacts.task_path),
        splits=request.splits,
        acceptance=request.split_acceptance,
    )

    generated_tasks = build_generated_tasks(experiment, base_task)
    task_paths = write_generated_tasks(experiment, generated_tasks)
    state = load_experiment_state(experiment.name)
    completed: dict[str, Any] = state.get("completed", {})
    attempts: list[dict[str, Any]] = state.get("attempts", [])
    failures = 0

    for task_payload, task_path in zip(generated_tasks, task_paths, strict=True):
        test_id = task_payload["test_id"]
        if test_id in completed:
            continue
        result = execute_run_task(
            str(task_path),
            allow_gui_clicks=allow_gui_clicks,
            timeout_seconds=timeout_seconds,
            execution_mode=execution_mode,
        )
        attempt = {
            "test_id": test_id,
            "task_path": str(task_path),
            "status": result.status,
            "exit_code": result.exit_code,
            "log_path": result.log_path,
            "screenshot_path": result.screenshot_path,
        }
        attempts.append(attempt)
        completed[test_id] = attempt
        state["completed"] = completed
        state["attempts"] = attempts
        save_experiment_state(experiment.name, state)
        update_leaderboard_csv()
        update_summary_md()

        if result.exit_code != 0:
            failures += 1
        if result.safety_ui_failure:
            limitations.append(f"Safety/UI failure on {test_id}.")
            report_path = write_research_report(request, experiment.name, [], limitations)
            print(f"research stopped on safety/UI failure at {test_id}")
            print(f"report: {report_path}")
            return 1
        if failures >= experiment.limits.stop_after_failures:
            limitations.append(f"Stopped after {failures} failures.")
            break

    top_rows = choose_top_candidate_rows(experiment.name, request.top_candidates_for_splits)
    candidate_ids = [row["test_id"] for row in top_rows]

    for row in top_rows:
        candidate_payload = build_task_payload(request)
        candidate_payload["test_id"] = row["test_id"]
        candidate_payload["name"] = row["task_name"]
        candidate_payload["inputs"] = json.loads(row["full_inputs_json"])
        candidate_task = validate_task_payload(candidate_payload)
        try:
            run_split_validation_for_candidate(
                split_experiment,
                candidate_task,
                row["test_id"],
                allow_gui_clicks=allow_gui_clicks,
                timeout_seconds=timeout_seconds,
                execution_mode=execution_mode,
            )
            summarize_candidate(row["test_id"])
        except Exception as exc:
            limitations.append(str(exc))
            break

    if request.stress_tests_required:
        limitations.append("Stress tests requested but not automated in Phase 11.")

    report_path = write_research_report(request, experiment.name, candidate_ids, limitations)
    print(f"research report: {report_path}")
    return 0
