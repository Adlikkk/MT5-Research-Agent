from __future__ import annotations

import argparse

from mt5_research_agent import __version__
from mt5_research_agent.background_runner import (
    run_agent_latest_results_command,
    run_agent_run_task_command,
    run_agent_task_status_command,
    run_compile_ea_command,
    run_create_smoke_task_command,
    run_find_reports_command,
    run_fix_smoke_task_command,
    run_generate_mt5_files_command,
    run_inspect_run_command,
    run_locate_ea_command,
    run_mt5_process_status_command,
    run_prepare_mt5_files_command,
    run_print_terminal_folders_command,
    run_preflight_task_command,
    run_print_ini_command,
    run_print_set_command,
    run_show_task_command,
    run_smoke_cli_command,
    run_stop_mt5_command,
    run_test_report_strategies_command,
    run_terminal_info_command,
)
from mt5_research_agent.api import run_serve_api_command
from mt5_research_agent.batch_runner import run_batch_status_command, run_run_batch_command
from mt5_research_agent.doctor import (
    has_hard_failure,
    render_doctor_json,
    render_doctor_report,
    run_doctor,
)
from mt5_research_agent.quickstart import (
    run_examples_command,
    run_first_smoke_command,
    run_open_artifacts_command,
    run_open_report_command,
)
from mt5_research_agent.ea_lab import (
    run_compile_ea_lab_command,
    run_create_ea_from_prompt_command,
    run_ea_lab_status_command,
    run_ea_version_history_command,
    run_improve_ea_command,
    run_revert_ea_command,
    run_smoke_test_ea_command,
)
from mt5_research_agent.goal_seeker import run_final_report_command, run_goal_seek_command
from mt5_research_agent.mcp_server import run_serve_mcp_command
from mt5_research_agent.optimizer import (
    run_optimization_spec_from_request_command,
    run_optimization_status_command,
    run_parse_optimization_command,
    run_plan_optimization_command,
    run_run_optimization_command,
)
from mt5_research_agent.experiment import (
    run_experiment_command,
    run_generate_tasks_command,
    run_validate_experiment_command,
)
from mt5_research_agent.inputs import (
    run_apply_inputs_command,
    run_calibrate_inputs_command,
    run_inputs_status_command,
    run_set_input_command,
    run_validate_task_command,
)
from mt5_research_agent.inspect import run_inspect_command
from mt5_research_agent.maintenance import (
    run_clean_artifacts_command,
    run_config_wizard_command,
    run_export_bundle_command,
)
from mt5_research_agent.reporting import (
    run_explain_decision_command,
    run_leaderboard_command,
    run_parse_report_command,
    run_summarize_candidate_command,
    run_summarize_command,
)
from mt5_research_agent.planner import run_plan_next_command, run_planned_command
from mt5_research_agent.providers import (
    run_ai_complete_command,
    run_ai_config_command,
    run_ai_status_command,
)
from mt5_research_agent.research_workflow import (
    run_candidate_report_command,
    run_create_research_request_command,
    run_plan_from_request_command,
    run_research_command,
    run_split_validate_command,
    run_validate_research_request_command,
)
from mt5_research_agent.run_task import run_task_command
from mt5_research_agent.session import (
    run_session_start_command,
    run_session_status_command,
    run_session_stop_command,
)
from mt5_research_agent.split_validation import run_run_splits_command
from mt5_research_agent.tester_settings import (
    run_apply_tester_settings_command,
    run_tester_settings_status_command,
)
from mt5_research_agent.tester import run_open_tester_command, run_tester_status_command


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="mt5_research_agent")
    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser("version", help="Show the package version")
    doctor_parser = subparsers.add_parser("doctor", help="Run local environment checks (PASS/WARN/FAIL)")
    doctor_parser.add_argument("--json", action="store_true", help="Emit the checks as JSON for agents")

    examples_parser = subparsers.add_parser("examples", help="Print a beginner-friendly command cheat sheet")
    examples_parser.add_argument("--json", action="store_true", help="Emit example requests/docs as JSON")
    first_smoke_parser = subparsers.add_parser(
        "first-smoke",
        help="Create (and optionally run) a guided first Strategy Tester smoke test",
    )
    first_smoke_parser.add_argument("--ea", default=None, help="EA name visible to the Strategy Tester")
    first_smoke_parser.add_argument("--symbol", default="US30")
    first_smoke_parser.add_argument("--timeframe", default="M15")
    first_smoke_parser.add_argument("--period-from", default="2024.01.01")
    first_smoke_parser.add_argument("--period-to", default="2024.02.01")
    first_smoke_parser.add_argument("--deposit", type=float, default=10000)
    first_smoke_parser.add_argument(
        "--model",
        default="1 minute OHLC",
        help="Tester model (default fast/deterministic '1 minute OHLC' for infra validation)",
    )
    first_smoke_parser.add_argument("--run", action="store_true", help="Launch MT5; without it, preview only")
    first_smoke_parser.add_argument("--dry-run", action="store_true", help="Write the task and print the plan; never launch MT5")
    first_smoke_parser.add_argument("--timeout-seconds", type=int, default=900)
    first_smoke_parser.add_argument("--json", action="store_true")
    open_report_parser = subparsers.add_parser("open-report", help="Open one run's report in the OS default app")
    open_report_parser.add_argument("test_id")
    open_report_parser.add_argument("--json", action="store_true")
    open_artifacts_parser = subparsers.add_parser(
        "open-artifacts", help="Open the artifacts and results folders in the OS file browser"
    )
    open_artifacts_parser.add_argument("--json", action="store_true")
    inspect_parser = subparsers.add_parser("inspect", help="Inspect an already-open MT5 window")
    inspect_parser.add_argument(
        "--backend",
        choices=("uia", "win32"),
        default="uia",
        help="pywinauto backend used for inspection",
    )
    inspect_parser.add_argument(
        "--dump-depth",
        type=int,
        default=2,
        help="Maximum child-control traversal depth",
    )
    tester_status_parser = subparsers.add_parser(
        "tester-status",
        help="Check whether the Strategy Tester panel appears visible",
    )
    tester_status_parser.add_argument(
        "--backend",
        choices=("uia", "win32"),
        default="win32",
        help="pywinauto backend used for inspection",
    )
    tester_status_parser.add_argument(
        "--dump-depth",
        type=int,
        default=3,
        help="Maximum child-control traversal depth",
    )
    open_tester_parser = subparsers.add_parser(
        "open-tester",
        help="Focus MT5 and send Ctrl+R to toggle/open Strategy Tester",
    )
    open_tester_parser.add_argument(
        "--allow-gui-clicks",
        action="store_true",
        help="Required safety flag before any GUI-affecting action is attempted",
    )
    open_tester_parser.add_argument(
        "--backend",
        choices=("uia", "win32"),
        default="win32",
        help="pywinauto backend used for inspection",
    )
    open_tester_parser.add_argument(
        "--dump-depth",
        type=int,
        default=3,
        help="Maximum child-control traversal depth",
    )
    subparsers.add_parser(
        "inputs-status",
        help="Inspect the Strategy Tester Inputs tab and report whether the inputs grid is readable",
    )
    set_input_parser = subparsers.add_parser(
        "set-input",
        help="Set one Strategy Tester input value",
    )
    set_input_parser.add_argument("--name", required=True, help="Input name to set")
    set_input_parser.add_argument("--value", required=True, help="New input value")
    set_input_parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Resolve and verify the target input without changing it",
    )
    set_input_parser.add_argument(
        "--allow-gui-clicks",
        action="store_true",
        help="Required safety flag before any GUI-affecting input edit is attempted",
    )
    subparsers.add_parser(
        "calibrate-inputs",
        help="Placeholder for a future calibrated fallback workflow",
    )
    validate_task_parser = subparsers.add_parser(
        "validate-task",
        help="Validate a research task JSON file",
    )
    validate_task_parser.add_argument("task_path", help="Path to the task JSON file")
    apply_inputs_parser = subparsers.add_parser(
        "apply-inputs",
        help="Apply all task input values through the Strategy Tester Inputs tab",
    )
    apply_inputs_parser.add_argument("task_path", help="Path to the task JSON file")
    apply_inputs_parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Resolve and verify all inputs without changing them",
    )
    apply_inputs_parser.add_argument(
        "--allow-gui-clicks",
        action="store_true",
        help="Required safety flag before any GUI-affecting input edits are attempted",
    )
    subparsers.add_parser(
        "tester-settings-status",
        help="Inspect the current Strategy Tester settings tab values",
    )
    apply_tester_settings_parser = subparsers.add_parser(
        "apply-tester-settings",
        help="Apply non-input Strategy Tester settings from a task JSON file",
    )
    apply_tester_settings_parser.add_argument("task_path", help="Path to the task JSON file")
    apply_tester_settings_parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Resolve and verify tester settings without changing them",
    )
    apply_tester_settings_parser.add_argument(
        "--allow-gui-clicks",
        action="store_true",
        help="Required safety flag before any GUI-affecting tester setting edits are attempted",
    )
    run_task_parser = subparsers.add_parser(
        "run-task",
        help="Run one Strategy Tester task end-to-end without report parsing",
    )
    run_task_parser.add_argument("task_path", help="Path to the task JSON file")
    run_task_parser.add_argument(
        "--execution-mode",
        choices=("cli", "gui"),
        default="cli",
        help="Use background CLI mode by default, or GUI mode as a guarded fallback",
    )
    run_task_parser.add_argument(
        "--allow-gui-clicks",
        action="store_true",
        help="Required safety flag before any GUI-affecting run is attempted in GUI mode",
    )
    run_task_parser.add_argument(
        "--timeout-seconds",
        type=int,
        default=1800,
        help="Conservative timeout while waiting for the backtest to finish",
    )
    run_task_parser.add_argument(
        "--allow-stop-existing-terminal",
        action="store_true",
        help="Stop the matching configured MT5 terminal before launching CLI mode",
    )
    run_task_parser.add_argument(
        "--keep-terminal-open",
        action="store_true",
        help="Generate the ini with ShutdownTerminal=0 in CLI mode",
    )
    parse_report_parser = subparsers.add_parser(
        "parse-report",
        help="Parse one MT5 HTML report into structured JSON metrics",
    )
    parse_report_parser.add_argument("report_path", help="Path to the raw MT5 HTML report")
    explain_decision_parser = subparsers.add_parser(
        "explain-decision",
        help="Explain the stored pass/fail decision for one test_id",
    )
    explain_decision_parser.add_argument("test_id")
    generate_mt5_files_parser = subparsers.add_parser(
        "generate-mt5-files",
        help="Generate MT5 .set and .ini files for one task",
    )
    generate_mt5_files_parser.add_argument("task_path", help="Path to the task JSON file")
    prepare_mt5_files_parser = subparsers.add_parser(
        "prepare-mt5-files",
        help="Generate artifact files, copy the native tester .set, and print MT5-compatible paths",
    )
    prepare_mt5_files_parser.add_argument("task_path", help="Path to the task JSON file")
    show_task_parser = subparsers.add_parser(
        "show-task",
        help="Print a compact summary for one task JSON file",
    )
    show_task_parser.add_argument("task_path", help="Path to the task JSON file")
    create_smoke_task_parser = subparsers.add_parser(
        "create-smoke-task",
        help="Create a minimal relaxed-acceptance smoke task JSON",
    )
    create_smoke_task_parser.add_argument("--test-id", required=True)
    create_smoke_task_parser.add_argument("--ea", required=True)
    create_smoke_task_parser.add_argument("--symbol", required=True)
    create_smoke_task_parser.add_argument("--timeframe", required=True)
    create_smoke_task_parser.add_argument("--period-from", required=True)
    create_smoke_task_parser.add_argument("--period-to", required=True)
    create_smoke_task_parser.add_argument("--deposit", required=True, type=float)
    inspect_run_parser = subparsers.add_parser(
        "inspect-run",
        help="Inspect the latest persisted attempt metadata for one test_id",
    )
    inspect_run_parser.add_argument("test_id")
    print_ini_parser = subparsers.add_parser(
        "print-ini",
        help="Generate and print the exact MT5 [Tester] ini content for one task",
    )
    print_ini_parser.add_argument("task_path")
    print_set_parser = subparsers.add_parser(
        "print-set",
        help="Generate and print the exact MT5 .set content for one task",
    )
    print_set_parser.add_argument("task_path")
    smoke_cli_parser = subparsers.add_parser(
        "smoke-cli",
        help="Generate MT5 files and preview or run one background CLI command",
    )
    smoke_cli_parser.add_argument("task_path", help="Path to the task JSON file")
    smoke_cli_parser.add_argument(
        "--run",
        action="store_true",
        help="Launch MT5 after generating files. Without this flag, only preview the command.",
    )
    smoke_cli_parser.add_argument(
        "--timeout-seconds",
        type=int,
        default=1800,
        help="Timeout when --run is used",
    )
    smoke_cli_parser.add_argument(
        "--allow-stop-existing-terminal",
        action="store_true",
        help="Stop the matching configured MT5 terminal before launching the background CLI run",
    )
    smoke_cli_parser.add_argument(
        "--keep-terminal-open",
        action="store_true",
        help="Generate the ini with ShutdownTerminal=0 for one-shot smoke diagnostics",
    )
    test_report_strategies_parser = subparsers.add_parser(
        "test-report-strategies",
        help="Try multiple MT5 report path strategies and stop at the first emitted report",
    )
    test_report_strategies_parser.add_argument("task_path", help="Path to the task JSON file")
    test_report_strategies_parser.add_argument(
        "--timeout-seconds",
        type=int,
        default=1800,
        help="Timeout per MT5 strategy attempt",
    )
    subparsers.add_parser(
        "terminal-info",
        help="Print MT5 terminal and candidate Experts folder information",
    )
    subparsers.add_parser(
        "print-terminal-folders",
        help="Print likely MT5 data, Experts, log, tester, and report folders",
    )
    find_reports_parser = subparsers.add_parser(
        "find-reports",
        help="Search likely MT5 report folders for recent report-like files",
    )
    find_reports_parser.add_argument("--since-minutes", type=int, default=60)
    subparsers.add_parser(
        "mt5-process-status",
        help="Inspect whether terminal64.exe is already running",
    )
    stop_mt5_parser = subparsers.add_parser(
        "stop-mt5",
        help="Stop the configured MT5 terminal process safely",
    )
    stop_mt5_parser.add_argument("--dry-run", action="store_true", help="Show which matching processes would be stopped")
    stop_mt5_parser.add_argument("--confirm", action="store_true", help="Actually stop the matching configured MT5 process")
    stop_mt5_parser.add_argument("--all", action="store_true", help="Also target unrelated terminal64.exe paths")
    locate_ea_parser = subparsers.add_parser(
        "locate-ea",
        help="Locate matching .mq5 and .ex5 files in likely MT5 Experts folders",
    )
    locate_ea_parser.add_argument("ea_name")
    compile_ea_parser = subparsers.add_parser(
        "compile-ea",
        help="Compile an EA source through MetaEditor when possible",
    )
    compile_ea_parser.add_argument("ea_name")
    preflight_task_parser = subparsers.add_parser(
        "preflight-task",
        help="Run deterministic EA, report-path, and symbol preflight checks for one task",
    )
    preflight_task_parser.add_argument("task_path")
    fix_smoke_task_parser = subparsers.add_parser(
        "fix-smoke-task",
        help="Create a patched smoke task when a better Expert= value is inferred",
    )
    fix_smoke_task_parser.add_argument("task_path")
    fix_smoke_task_parser.add_argument(
        "--in-place",
        action="store_true",
        help="Update the existing task instead of creating a -FIXED copy",
    )
    agent_run_task_parser = subparsers.add_parser(
        "agent-run-task",
        help="Run one task and emit concise JSON for agent orchestration",
    )
    agent_run_task_parser.add_argument("task_path")
    agent_run_task_parser.add_argument(
        "--timeout-seconds",
        type=int,
        default=1800,
        help="Timeout for the CLI background task",
    )
    agent_task_status_parser = subparsers.add_parser(
        "agent-task-status",
        help="Print concise JSON status for one stored test_id",
    )
    agent_task_status_parser.add_argument("test_id")
    subparsers.add_parser(
        "agent-latest-results",
        help="Print concise JSON for the latest stored results",
    )
    subparsers.add_parser(
        "leaderboard",
        help="Refresh the CSV leaderboard from stored SQLite run results",
    )
    subparsers.add_parser(
        "summarize",
        help="Refresh the Markdown summary from stored SQLite run results",
    )
    validate_experiment_parser = subparsers.add_parser(
        "validate-experiment",
        help="Validate an experiment JSON file",
    )
    validate_experiment_parser.add_argument("experiment_path", help="Path to the experiment JSON file")
    generate_tasks_parser = subparsers.add_parser(
        "generate-tasks",
        help="Generate deterministic task variants from an experiment JSON file",
    )
    generate_tasks_parser.add_argument("experiment_path", help="Path to the experiment JSON file")
    run_experiment_parser = subparsers.add_parser(
        "run-experiment",
        help="Run deterministic matrix-generated tasks sequentially",
    )
    run_experiment_parser.add_argument("experiment_path", help="Path to the experiment JSON file")
    run_experiment_parser.add_argument(
        "--allow-gui-clicks",
        action="store_true",
        help="Required safety flag before any GUI-affecting experiment run is attempted",
    )
    run_experiment_parser.add_argument(
        "--timeout-seconds",
        type=int,
        default=1800,
        help="Per-task timeout while waiting for each backtest to finish",
    )
    run_splits_parser = subparsers.add_parser(
        "run-splits",
        help="Run one candidate across multiple fixed date splits",
    )
    run_splits_parser.add_argument("experiment_path", help="Path to the split experiment JSON file")
    run_splits_parser.add_argument(
        "--allow-gui-clicks",
        action="store_true",
        help="Required safety flag before any GUI-affecting split run is attempted",
    )
    run_splits_parser.add_argument(
        "--timeout-seconds",
        type=int,
        default=1800,
        help="Per-split timeout while waiting for each backtest to finish",
    )
    summarize_candidate_parser = subparsers.add_parser(
        "summarize-candidate",
        help="Write a Markdown summary for one stored candidate ID",
    )
    summarize_candidate_parser.add_argument("candidate_id", help="Candidate ID to summarize")
    split_validate_parser = subparsers.add_parser(
        "split-validate",
        help="Run split validation for an already-tested candidate using a request's splits",
    )
    split_validate_parser.add_argument("candidate_id", help="Stored full-period candidate test_id")
    split_validate_parser.add_argument(
        "--request",
        required=True,
        help="Path to the markdown research request that defines splits and acceptance",
    )
    split_validate_parser.add_argument(
        "--allow-gui-clicks",
        action="store_true",
        help="Required safety flag before any GUI-affecting split run is attempted",
    )
    split_validate_parser.add_argument(
        "--timeout-seconds",
        type=int,
        default=1800,
        help="Per-split timeout while waiting for each backtest to finish",
    )
    candidate_report_parser = subparsers.add_parser(
        "candidate-report",
        help="Write a Markdown report for one stored candidate ID",
    )
    candidate_report_parser.add_argument("candidate_id", help="Candidate ID to report on")
    create_request_parser = subparsers.add_parser(
        "create-research-request",
        help="Scaffold a structured research request markdown file from a prompt",
    )
    create_request_parser.add_argument("prompt_path", help="Path to a free-text prompt markdown file")
    validate_request_parser = subparsers.add_parser(
        "validate-research-request",
        help="Validate a markdown research request and report TODOs",
    )
    validate_request_parser.add_argument("request_path", help="Path to the markdown research request file")
    plan_request_parser = subparsers.add_parser(
        "plan-from-request",
        help="Parse a markdown research request into deterministic draft plan files",
    )
    plan_request_parser.add_argument("request_path", help="Path to the markdown research request file")
    run_research_parser = subparsers.add_parser(
        "run-research",
        help="Run a markdown research request through deterministic testing and split validation",
    )
    run_research_parser.add_argument("request_path", help="Path to the markdown research request file")
    run_research_parser.add_argument(
        "--allow-gui-clicks",
        action="store_true",
        help="Required safety flag before any GUI-affecting research run is attempted",
    )
    run_research_parser.add_argument(
        "--timeout-seconds",
        type=int,
        default=1800,
        help="Per-test timeout while waiting for each backtest to finish",
    )
    run_research_parser.add_argument(
        "--session",
        action="store_true",
        help="Reuse the open research session terminal (GUI) instead of restarting MT5 per test",
    )
    plan_next_parser = subparsers.add_parser(
        "plan-next",
        help="Use previous deterministic results to propose the next explainable batch",
    )
    plan_next_parser.add_argument("--request", required=True, help="Path to the markdown research request file")
    run_planned_parser = subparsers.add_parser(
        "run-planned",
        help="Run a generated experiment plan JSON",
    )
    run_planned_parser.add_argument("experiment_path", help="Path to a generated experiment JSON file")
    run_planned_parser.add_argument(
        "--allow-gui-clicks",
        action="store_true",
        help="Required safety flag before any GUI-affecting planned run is attempted",
    )
    run_planned_parser.add_argument(
        "--timeout-seconds",
        type=int,
        default=1800,
        help="Per-test timeout while waiting for each backtest to finish",
    )
    run_batch_parser = subparsers.add_parser(
        "run-batch",
        help="Run a small bounded batch of pre-generated task JSON files",
    )
    run_batch_parser.add_argument("task_dir", help="Directory containing task JSON files")
    run_batch_parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Maximum number of eligible tasks to run in this batch",
    )
    run_batch_parser.add_argument(
        "--execution-mode",
        choices=("cli", "gui"),
        default="cli",
        help="Use background CLI mode by default, or GUI mode as a guarded fallback",
    )
    run_batch_parser.add_argument(
        "--dry-run",
        action="store_true",
        help="List which tasks would run without launching MT5",
    )
    run_batch_parser.add_argument(
        "--rerun",
        action="store_true",
        help="Re-run tasks even if they already have a completed result",
    )
    run_batch_parser.add_argument(
        "--allow-gui-clicks",
        action="store_true",
        help="Required safety flag before any GUI-affecting batch run is attempted",
    )
    run_batch_parser.add_argument(
        "--timeout-seconds",
        type=int,
        default=1800,
        help="Per-task timeout while waiting for each backtest to finish",
    )
    run_batch_parser.add_argument(
        "--session",
        action="store_true",
        help="Reuse the open research session terminal (GUI) instead of restarting MT5 per test",
    )
    subparsers.add_parser(
        "batch-status",
        help="Show the status of the most recent batch run",
    )

    session_start_parser = subparsers.add_parser(
        "session-start",
        help="Open the configured research MT5 terminal once and keep it alive for the session",
    )
    session_start_parser.add_argument(
        "--confirm",
        action="store_true",
        help="Adopt an already-running matching terminal instead of refusing",
    )
    session_start_parser.add_argument("--json", action="store_true")
    session_status_parser = subparsers.add_parser(
        "session-status",
        help="Show the research session terminal status",
    )
    session_status_parser.add_argument("--json", action="store_true")
    session_stop_parser = subparsers.add_parser(
        "session-stop",
        help="Stop ONLY the configured research terminal (never unrelated MT5 instances)",
    )
    session_stop_parser.add_argument(
        "--confirm",
        action="store_true",
        help="Required to actually stop the research terminal",
    )
    session_stop_parser.add_argument("--json", action="store_true")
    goal_seek_parser = subparsers.add_parser(
        "run-goal-seek",
        help="Iterate toward a research goal and produce a final report",
    )
    goal_seek_parser.add_argument("request_path", help="Path to the markdown research request file")
    goal_seek_parser.add_argument(
        "--max-rounds",
        type=int,
        default=3,
        help="Maximum exploratory/refinement rounds",
    )
    goal_seek_parser.add_argument(
        "--allow-gui-clicks",
        action="store_true",
        help="Required safety flag before any GUI-affecting goal-seek run is attempted",
    )
    goal_seek_parser.add_argument(
        "--timeout-seconds",
        type=int,
        default=1800,
        help="Per-test timeout while waiting for each backtest to finish",
    )
    final_report_parser = subparsers.add_parser(
        "final-report",
        help="Write a final goal report from stored runs without launching MT5",
    )
    final_report_parser.add_argument(
        "--request",
        required=True,
        help="Path to the markdown research request file",
    )

    opt_from_request_parser = subparsers.add_parser(
        "optimization-spec-from-request",
        help="Derive an MT5 optimization spec (numeric ranges) from a research request",
    )
    opt_from_request_parser.add_argument("request_path", help="Path to the markdown research request file")
    opt_from_request_parser.add_argument(
        "--algorithm",
        choices=("fast_genetic", "slow_complete", "all_symbols", "disabled"),
        default="fast_genetic",
        help="MT5 optimization algorithm",
    )
    opt_from_request_parser.add_argument(
        "--criterion",
        choices=(
            "balance_max",
            "balance_pf_max",
            "balance_payoff_max",
            "balance_dd_min",
            "balance_recovery_max",
            "balance_sharpe_max",
            "custom_max",
            "complex_max",
        ),
        default="balance_max",
        help="MT5 optimization criterion",
    )
    plan_optimization_parser = subparsers.add_parser(
        "plan-optimization",
        help="Preview the generated .set/.ini and grid size for an optimization spec (no MT5 launch)",
    )
    plan_optimization_parser.add_argument("spec_path", help="Path to the optimization spec JSON file")
    run_optimization_parser = subparsers.add_parser(
        "run-optimization",
        help="Run one MT5 optimization (many combos in a single launch) and rank its passes",
    )
    run_optimization_parser.add_argument("spec_path", help="Path to the optimization spec JSON file")
    run_optimization_parser.add_argument(
        "--run",
        action="store_true",
        help="Launch MT5 after generating files. Without this flag, only preview the command.",
    )
    run_optimization_parser.add_argument(
        "--timeout-seconds",
        type=int,
        default=3600,
        help="Timeout while waiting for the single optimization launch to finish",
    )
    run_optimization_parser.add_argument(
        "--allow-stop-existing-terminal",
        action="store_true",
        help="Stop the matching configured MT5 terminal before launching the optimization",
    )
    parse_optimization_parser = subparsers.add_parser(
        "parse-optimization",
        help="Parse and rank an existing MT5 optimization report (.xml) into passes",
    )
    parse_optimization_parser.add_argument("report_path", help="Path to the MT5 optimization report XML")
    parse_optimization_parser.add_argument("--limit", type=int, default=10, help="Top passes to print")
    parse_optimization_parser.add_argument("--min-profit-factor", type=float, default=None)
    parse_optimization_parser.add_argument("--max-dd", dest="max_equity_dd_pct", type=float, default=None)
    parse_optimization_parser.add_argument("--min-trades", type=float, default=None)
    optimization_status_parser = subparsers.add_parser(
        "optimization-status",
        help="Show the stored result of the most recent optimization for a test_id",
    )
    optimization_status_parser.add_argument("test_id")

    create_ea_parser = subparsers.add_parser(
        "create-ea-from-prompt",
        help="Generate a safe-by-default EA from a prompt markdown file",
    )
    create_ea_parser.add_argument("prompt_path", help="Path to the EA prompt markdown file")
    smoke_ea_parser = subparsers.add_parser(
        "smoke-test-ea",
        help="Create and optionally run a smoke test for an EA Lab EA",
    )
    smoke_ea_parser.add_argument("ea_name")
    smoke_ea_parser.add_argument("--symbol", required=True)
    smoke_ea_parser.add_argument("--timeframe", required=True)
    smoke_ea_parser.add_argument("--period-from", default="2024.01.01")
    smoke_ea_parser.add_argument("--period-to", default="2024.02.01")
    smoke_ea_parser.add_argument("--deposit", type=float, default=10000)
    smoke_ea_parser.add_argument(
        "--run",
        action="store_true",
        help="Launch MT5 after generating the smoke task. Without this flag, only preview.",
    )
    smoke_ea_parser.add_argument("--timeout-seconds", type=int, default=900)
    improve_ea_parser = subparsers.add_parser(
        "improve-ea",
        help="Run goal-driven parameter search to improve an EA",
    )
    improve_ea_parser.add_argument("ea_name")
    improve_ea_parser.add_argument("--goal", required=True, help="Path to a research request markdown file")
    improve_ea_parser.add_argument("--max-rounds", type=int, default=3)
    improve_ea_parser.add_argument("--allow-gui-clicks", action="store_true")
    improve_ea_parser.add_argument("--timeout-seconds", type=int, default=1800)
    ea_lab_status_parser = subparsers.add_parser(
        "ea-lab-status",
        help="Show the current EA Lab status for one EA",
    )
    ea_lab_status_parser.add_argument("ea_name")
    ea_version_history_parser = subparsers.add_parser(
        "ea-version-history",
        help="List version history for one EA Lab EA",
    )
    ea_version_history_parser.add_argument("ea_name")
    revert_ea_parser = subparsers.add_parser(
        "revert-ea",
        help="Revert an EA Lab EA to a previous version",
    )
    revert_ea_parser.add_argument("ea_name")
    revert_ea_parser.add_argument("--to-version", type=int, required=True)
    compile_ea_lab_parser = subparsers.add_parser(
        "compile-ea-lab",
        help="Compile the current EA Lab version and record the result",
    )
    compile_ea_lab_parser.add_argument("ea_name")

    export_bundle_parser = subparsers.add_parser(
        "export-bundle",
        help="Zip the artifacts for one run test_id or research request slug",
    )
    export_bundle_parser.add_argument("identifier", help="A run test_id or a research request slug")
    clean_artifacts_parser = subparsers.add_parser(
        "clean-artifacts",
        help="Remove regeneratable MT5 scaffolding; reports and logs are preserved",
    )
    clean_artifacts_parser.add_argument(
        "--safe",
        action="store_true",
        help="Actually delete regeneratable scaffolding (without this flag, preview only)",
    )
    config_wizard_parser = subparsers.add_parser(
        "config-wizard",
        help="Detect MT5 and write/update config.json without clobbering existing values",
    )
    config_wizard_parser.add_argument("--terminal-path", default=None)
    config_wizard_parser.add_argument("--artifacts-dir", default=None)
    config_wizard_parser.add_argument("--results-dir", default=None)
    config_wizard_parser.add_argument("--portable", dest="portable", action="store_true", default=None)

    serve_api_parser = subparsers.add_parser(
        "serve-api",
        help="Serve the localhost-only JSON API for agent integration",
    )
    serve_api_parser.add_argument("--host", default="127.0.0.1")
    serve_api_parser.add_argument("--port", type=int, default=8765)

    serve_mcp_parser = subparsers.add_parser(
        "serve-mcp",
        help="Serve the safe MCP tool surface over stdio (JSON-RPC) for MCP clients",
    )
    serve_mcp_parser.add_argument(
        "--selfcheck",
        action="store_true",
        help="Run the MCP handshake in-process and print health JSON, then exit",
    )

    subparsers.add_parser(
        "ai-status",
        help="Show the optional AI provider configuration and usage (no secrets)",
    )
    ai_config_parser = subparsers.add_parser(
        "ai-config",
        help="Configure the optional AI provider (keys are read from env, never stored)",
    )
    ai_config_parser.add_argument(
        "--provider",
        choices=("none", "openai", "anthropic", "openrouter", "groq", "ollama", "custom"),
        default=None,
    )
    ai_config_parser.add_argument("--model", default=None)
    ai_config_parser.add_argument("--base-url", dest="base_url", default=None)
    ai_config_parser.add_argument("--api-key-env", dest="api_key_env", default=None)
    ai_config_parser.add_argument("--max-calls", dest="max_calls", type=int, default=None)
    ai_config_parser.add_argument("--max-cost", dest="max_cost_usd", type=float, default=None)
    ai_config_parser.add_argument("--usd-per-1k-tokens", dest="usd_per_1k_tokens", type=float, default=None)
    ai_config_parser.add_argument("--enable", action="store_true")
    ai_config_parser.add_argument("--disable", action="store_true")
    ai_config_parser.add_argument("--allow-autonomous", action="store_true")
    ai_config_parser.add_argument("--no-autonomous", action="store_true")
    ai_complete_parser = subparsers.add_parser(
        "ai-complete",
        help="Run one guarded AI completion from a prompt file (requires an enabled provider)",
    )
    ai_complete_parser.add_argument("prompt_path", help="Path to a prompt file (or literal prompt text)")
    ai_complete_parser.add_argument("--system", default=None, help="Optional extra system instruction")

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.command == "version":
        print(__version__)
        return 0

    if args.command == "doctor":
        checks = run_doctor()
        print(render_doctor_json(checks) if args.json else render_doctor_report(checks))
        # WARN-only checks (missing terminal, auto-created dirs) do not fail.
        return 1 if has_hard_failure(checks) else 0

    if args.command == "examples":
        return run_examples_command(as_json=args.json)

    if args.command == "first-smoke":
        return run_first_smoke_command(
            ea=args.ea,
            symbol=args.symbol,
            timeframe=args.timeframe,
            period_from=args.period_from,
            period_to=args.period_to,
            deposit=args.deposit,
            run=args.run,
            dry_run=args.dry_run,
            timeout_seconds=args.timeout_seconds,
            model=args.model,
            as_json=args.json,
        )

    if args.command == "open-report":
        return run_open_report_command(args.test_id, as_json=args.json)

    if args.command == "open-artifacts":
        return run_open_artifacts_command(as_json=args.json)

    if args.command == "inspect":
        return run_inspect_command(backend=args.backend, dump_depth=args.dump_depth)

    if args.command == "tester-status":
        return run_tester_status_command(backend=args.backend, dump_depth=args.dump_depth)

    if args.command == "open-tester":
        return run_open_tester_command(
            allow_gui_clicks=args.allow_gui_clicks,
            backend=args.backend,
            dump_depth=args.dump_depth,
        )

    if args.command == "inputs-status":
        return run_inputs_status_command()

    if args.command == "set-input":
        return run_set_input_command(
            name=args.name,
            value=args.value,
            dry_run=args.dry_run,
            allow_gui_clicks=args.allow_gui_clicks,
        )

    if args.command == "calibrate-inputs":
        return run_calibrate_inputs_command()

    if args.command == "validate-task":
        return run_validate_task_command(args.task_path)

    if args.command == "apply-inputs":
        return run_apply_inputs_command(
            task_path=args.task_path,
            dry_run=args.dry_run,
            allow_gui_clicks=args.allow_gui_clicks,
        )

    if args.command == "tester-settings-status":
        return run_tester_settings_status_command()

    if args.command == "apply-tester-settings":
        return run_apply_tester_settings_command(
            task_path=args.task_path,
            dry_run=args.dry_run,
            allow_gui_clicks=args.allow_gui_clicks,
        )

    if args.command == "run-task":
        return run_task_command(
            task_path=args.task_path,
            allow_gui_clicks=args.allow_gui_clicks,
            timeout_seconds=args.timeout_seconds,
            execution_mode=args.execution_mode,
            allow_stop_existing_terminal=args.allow_stop_existing_terminal,
            keep_terminal_open=args.keep_terminal_open,
        )

    if args.command == "generate-mt5-files":
        return run_generate_mt5_files_command(args.task_path)

    if args.command == "prepare-mt5-files":
        return run_prepare_mt5_files_command(args.task_path)

    if args.command == "show-task":
        return run_show_task_command(args.task_path)

    if args.command == "create-smoke-task":
        return run_create_smoke_task_command(
            test_id=args.test_id,
            ea=args.ea,
            symbol=args.symbol,
            timeframe=args.timeframe,
            period_from=args.period_from,
            period_to=args.period_to,
            deposit=args.deposit,
        )

    if args.command == "inspect-run":
        return run_inspect_run_command(args.test_id)

    if args.command == "print-ini":
        return run_print_ini_command(args.task_path)

    if args.command == "print-set":
        return run_print_set_command(args.task_path)

    if args.command == "smoke-cli":
        return run_smoke_cli_command(
            task_path=args.task_path,
            run=args.run,
            timeout_seconds=args.timeout_seconds,
            allow_stop_existing_terminal=args.allow_stop_existing_terminal,
            keep_terminal_open=args.keep_terminal_open,
        )

    if args.command == "test-report-strategies":
        return run_test_report_strategies_command(args.task_path, args.timeout_seconds)

    if args.command == "terminal-info":
        return run_terminal_info_command()

    if args.command == "print-terminal-folders":
        return run_print_terminal_folders_command()

    if args.command == "find-reports":
        return run_find_reports_command(args.since_minutes)

    if args.command == "mt5-process-status":
        return run_mt5_process_status_command()

    if args.command == "stop-mt5":
        return run_stop_mt5_command(confirm=args.confirm and not args.dry_run, all_processes=args.all)

    if args.command == "locate-ea":
        return run_locate_ea_command(args.ea_name)

    if args.command == "compile-ea":
        return run_compile_ea_command(args.ea_name)

    if args.command == "preflight-task":
        return run_preflight_task_command(args.task_path)

    if args.command == "fix-smoke-task":
        return run_fix_smoke_task_command(args.task_path, args.in_place)

    if args.command == "agent-run-task":
        return run_agent_run_task_command(args.task_path, args.timeout_seconds)

    if args.command == "agent-task-status":
        return run_agent_task_status_command(args.test_id)

    if args.command == "agent-latest-results":
        return run_agent_latest_results_command()

    if args.command == "parse-report":
        return run_parse_report_command(args.report_path)

    if args.command == "explain-decision":
        return run_explain_decision_command(args.test_id)

    if args.command == "leaderboard":
        return run_leaderboard_command()

    if args.command == "summarize":
        return run_summarize_command()

    if args.command == "validate-experiment":
        return run_validate_experiment_command(args.experiment_path)

    if args.command == "generate-tasks":
        return run_generate_tasks_command(args.experiment_path)

    if args.command == "run-experiment":
        return run_experiment_command(
            experiment_path=args.experiment_path,
            allow_gui_clicks=args.allow_gui_clicks,
            timeout_seconds=args.timeout_seconds,
        )

    if args.command == "run-splits":
        return run_run_splits_command(
            experiment_path=args.experiment_path,
            allow_gui_clicks=args.allow_gui_clicks,
            timeout_seconds=args.timeout_seconds,
        )

    if args.command == "summarize-candidate":
        return run_summarize_candidate_command(args.candidate_id)

    if args.command == "split-validate":
        return run_split_validate_command(
            candidate_id=args.candidate_id,
            request_path=args.request,
            allow_gui_clicks=args.allow_gui_clicks,
            timeout_seconds=args.timeout_seconds,
        )

    if args.command == "candidate-report":
        return run_candidate_report_command(args.candidate_id)

    if args.command == "create-research-request":
        return run_create_research_request_command(args.prompt_path)

    if args.command == "validate-research-request":
        return run_validate_research_request_command(args.request_path)

    if args.command == "plan-from-request":
        return run_plan_from_request_command(args.request_path)

    if args.command == "run-research":
        return run_research_command(
            request_path=args.request_path,
            allow_gui_clicks=args.allow_gui_clicks,
            timeout_seconds=args.timeout_seconds,
            session=args.session,
        )

    if args.command == "plan-next":
        return run_plan_next_command(args.request)

    if args.command == "run-planned":
        return run_planned_command(
            experiment_path=args.experiment_path,
            allow_gui_clicks=args.allow_gui_clicks,
            timeout_seconds=args.timeout_seconds,
        )

    if args.command == "run-batch":
        return run_run_batch_command(
            task_dir=args.task_dir,
            limit=args.limit,
            execution_mode=args.execution_mode,
            dry_run=args.dry_run,
            rerun=args.rerun,
            allow_gui_clicks=args.allow_gui_clicks,
            timeout_seconds=args.timeout_seconds,
            session=args.session,
        )

    if args.command == "batch-status":
        return run_batch_status_command()

    if args.command == "session-start":
        return run_session_start_command(confirm=args.confirm, as_json=args.json)

    if args.command == "session-status":
        return run_session_status_command(as_json=args.json)

    if args.command == "session-stop":
        return run_session_stop_command(confirm=args.confirm, as_json=args.json)

    if args.command == "run-goal-seek":
        return run_goal_seek_command(
            request_path=args.request_path,
            max_rounds=args.max_rounds,
            allow_gui_clicks=args.allow_gui_clicks,
            timeout_seconds=args.timeout_seconds,
        )

    if args.command == "final-report":
        return run_final_report_command(args.request)

    if args.command == "optimization-spec-from-request":
        return run_optimization_spec_from_request_command(
            args.request_path,
            algorithm=args.algorithm,
            criterion=args.criterion,
        )

    if args.command == "plan-optimization":
        return run_plan_optimization_command(args.spec_path)

    if args.command == "run-optimization":
        return run_run_optimization_command(
            args.spec_path,
            run=args.run,
            timeout_seconds=args.timeout_seconds,
            allow_stop_existing_terminal=args.allow_stop_existing_terminal,
        )

    if args.command == "parse-optimization":
        return run_parse_optimization_command(
            args.report_path,
            limit=args.limit,
            min_profit_factor=args.min_profit_factor,
            max_equity_dd_pct=args.max_equity_dd_pct,
            min_trades=args.min_trades,
        )

    if args.command == "optimization-status":
        return run_optimization_status_command(args.test_id)

    if args.command == "create-ea-from-prompt":
        return run_create_ea_from_prompt_command(args.prompt_path)

    if args.command == "smoke-test-ea":
        return run_smoke_test_ea_command(
            args.ea_name,
            symbol=args.symbol,
            timeframe=args.timeframe,
            period_from=args.period_from,
            period_to=args.period_to,
            deposit=args.deposit,
            run=args.run,
            timeout_seconds=args.timeout_seconds,
        )

    if args.command == "improve-ea":
        return run_improve_ea_command(
            args.ea_name,
            goal_request=args.goal,
            max_rounds=args.max_rounds,
            allow_gui_clicks=args.allow_gui_clicks,
            timeout_seconds=args.timeout_seconds,
        )

    if args.command == "ea-lab-status":
        return run_ea_lab_status_command(args.ea_name)

    if args.command == "ea-version-history":
        return run_ea_version_history_command(args.ea_name)

    if args.command == "revert-ea":
        return run_revert_ea_command(args.ea_name, args.to_version)

    if args.command == "compile-ea-lab":
        return run_compile_ea_lab_command(args.ea_name)

    if args.command == "export-bundle":
        return run_export_bundle_command(args.identifier)

    if args.command == "clean-artifacts":
        return run_clean_artifacts_command(args.safe)

    if args.command == "config-wizard":
        return run_config_wizard_command(
            terminal_path=args.terminal_path,
            artifacts_dir=args.artifacts_dir,
            results_dir=args.results_dir,
            portable=args.portable,
        )

    if args.command == "serve-api":
        return run_serve_api_command(host=args.host, port=args.port)

    if args.command == "serve-mcp":
        return run_serve_mcp_command(selfcheck=args.selfcheck)

    if args.command == "ai-status":
        return run_ai_status_command()

    if args.command == "ai-config":
        return run_ai_config_command(
            provider=args.provider,
            model=args.model,
            base_url=args.base_url,
            api_key_env=args.api_key_env,
            max_calls=args.max_calls,
            max_cost_usd=args.max_cost_usd,
            usd_per_1k_tokens=args.usd_per_1k_tokens,
            enable=args.enable,
            disable=args.disable,
            allow_autonomous=args.allow_autonomous,
            no_autonomous=args.no_autonomous,
        )

    if args.command == "ai-complete":
        return run_ai_complete_command(args.prompt_path, system=args.system)

    parser.error(f"Unknown command: {args.command}")
    return 2
