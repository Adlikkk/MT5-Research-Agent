from __future__ import annotations

import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any
from typing import Callable

from mt5_research_agent.background_runner import coerce_acceptance_evaluation, run_task_cli
from mt5_research_agent.config import load_config
from mt5_research_agent.inputs import build_inputs_artifact_paths, find_mt5_window, find_tester_control, run_apply_inputs_command
from mt5_research_agent.inspect import build_not_found_message, normalize_text, utc_timestamp
from mt5_research_agent.report_parser import parse_report_file
from mt5_research_agent.result_store import (
    build_stored_run,
    evaluate_acceptance,
    make_test_id,
    store_parsed_report_json,
    store_run,
    update_leaderboard_csv,
    update_summary_md,
)
from mt5_research_agent.task import load_task, task_to_payload
from mt5_research_agent.tester import detect_tester_visibility, save_window_screenshot, write_json
from mt5_research_agent.tester_settings import fold_text, run_apply_tester_settings_command


READY_BUTTON_LABELS = {"zacatek", "start"}
RUNNING_BUTTON_LABELS = {"stop", "zastavit"}


@dataclass(slots=True)
class StartButtonSnapshot:
    text: str
    folded_text: str
    enabled: bool
    visible: bool


@dataclass(slots=True)
class RunTaskResult:
    exit_code: int
    status: str
    test_id: str
    raw_report_path: str
    log_path: str
    screenshot_path: str
    safety_ui_failure: bool


def normalize_button_label(value: str) -> str:
    return fold_text(value).casefold().replace(" ", "")


def is_ready_state(snapshot: StartButtonSnapshot) -> bool:
    return snapshot.folded_text in READY_BUTTON_LABELS and snapshot.enabled and snapshot.visible


def is_running_state(snapshot: StartButtonSnapshot) -> bool:
    return snapshot.folded_text in RUNNING_BUTTON_LABELS or not is_ready_state(snapshot)


def find_start_button(tester_win32):
    candidates = []
    for control in tester_win32.descendants():
        try:
            if control.class_name() != "Button" or not control.is_visible():
                continue
            text = normalize_text(control.window_text())
            folded = normalize_button_label(text)
            candidates.append((folded in READY_BUTTON_LABELS or folded in RUNNING_BUTTON_LABELS, text, control))
        except Exception:
            continue

    preferred = [control for is_match, _, control in candidates if is_match]
    if preferred:
        return preferred[-1]
    return candidates[-1][2] if candidates else None


def snapshot_start_button(button) -> StartButtonSnapshot:
    text = normalize_text(button.window_text())
    return StartButtonSnapshot(
        text=text,
        folded_text=normalize_button_label(text),
        enabled=bool(button.is_enabled()),
        visible=bool(button.is_visible()),
    )


def capture_button_state(window_win32):
    tester = find_tester_control(window_win32)
    if tester is None:
        raise RuntimeError("Unable to locate the Strategy Tester control while checking run state.")
    button = find_start_button(tester)
    if button is None:
        raise RuntimeError("Unable to locate the Strategy Tester Start button.")
    return button, snapshot_start_button(button)


def wait_for_state(window_win32, expected: str, timeout_seconds: int, poll_seconds: float = 1.0) -> tuple[bool, list[dict[str, Any]]]:
    deadline = time.monotonic() + timeout_seconds
    samples: list[dict[str, Any]] = []
    stable_ready = 0

    while time.monotonic() < deadline:
        _, snapshot = capture_button_state(window_win32)
        sample = {
            "timestamp": utc_timestamp(),
            "text": snapshot.text,
            "folded_text": snapshot.folded_text,
            "enabled": snapshot.enabled,
            "visible": snapshot.visible,
        }
        samples.append(sample)

        if expected == "started":
            if is_running_state(snapshot):
                return True, samples
        elif expected == "finished":
            if is_ready_state(snapshot):
                stable_ready += 1
                if stable_ready >= 3:
                    return True, samples
            else:
                stable_ready = 0

        time.sleep(poll_seconds)

    return False, samples


def prepare_run_window():
    config = load_config()
    window_win32 = find_mt5_window("win32", config)
    if window_win32 is None:
        raise RuntimeError(build_not_found_message(config, "win32"))

    status = detect_tester_visibility(window_win32, dump_depth=3)
    if not status.is_visible:
        raise RuntimeError("Strategy Tester is not visible. Run `python -m mt5_research_agent open-tester --allow-gui-clicks` first.")

    return config, window_win32


def locate_raw_report(config, started_at: float) -> Path | None:
    reports_dir = Path(config.artifacts_dir).resolve() / "raw_reports"
    reports_dir.mkdir(parents=True, exist_ok=True)
    candidates = [
        path for path in reports_dir.glob("*")
        if path.is_file() and path.suffix.lower() in {".htm", ".html"}
    ]
    candidates = [path for path in candidates if path.stat().st_mtime >= started_at - 2]
    if not candidates:
        return None
    return max(candidates, key=lambda path: path.stat().st_mtime)


def execute_run_task(
    task_path: str,
    allow_gui_clicks: bool,
    timeout_seconds: int,
    *,
    execution_mode: str = "cli",
    allow_stop_existing_terminal: bool = False,
    keep_terminal_open: bool = False,
    run_kind: str = "full_period",
    parent_candidate_id: str = "",
    split_id: str = "",
    acceptance_evaluator: Callable[[Any, Any], tuple[bool, str]] | None = None,
) -> RunTaskResult:
    if execution_mode == "cli":
        cli_result = run_task_cli(
            task_path,
            timeout_seconds,
            allow_stop_existing_terminal=allow_stop_existing_terminal,
            keep_terminal_open=keep_terminal_open,
            run_kind=run_kind,
            parent_candidate_id=parent_candidate_id,
            split_id=split_id,
            acceptance_evaluator=acceptance_evaluator,
        )
        return RunTaskResult(
            exit_code=cli_result.exit_code,
            status=cli_result.status,
            test_id=cli_result.test_id,
            raw_report_path=cli_result.raw_report_path,
            log_path=cli_result.log_path,
            screenshot_path="",
            safety_ui_failure=cli_result.safety_ui_failure,
        )

    if not allow_gui_clicks:
        return RunTaskResult(2, "safety_blocked", "", "", "", "", True)

    timestamp = utc_timestamp()
    config = load_config()
    artifact_paths = build_inputs_artifact_paths(config, timestamp, action="run_task")

    try:
        task = load_task(task_path)
        _, window_win32 = prepare_run_window()
        save_window_screenshot(window_win32, artifact_paths["before_screenshot"])

        settings_exit = run_apply_tester_settings_command(task_path, dry_run=False, allow_gui_clicks=True)
        if settings_exit != 0:
            save_window_screenshot(window_win32, artifact_paths["after_screenshot"])
            payload = {
                "timestamp": timestamp,
                "task_path": str(Path(task_path)),
                "task": task_to_payload(task),
                "phase": "apply_tester_settings",
                "exit_code": settings_exit,
                "before_screenshot_path": str(artifact_paths["before_screenshot"]),
                "after_screenshot_path": str(artifact_paths["after_screenshot"]),
                "status": "failed",
            }
            write_json(artifact_paths["log"], payload)
            return RunTaskResult(
                exit_code=1,
                status="apply_tester_settings_failed",
                test_id=task.test_id or "",
                raw_report_path="",
                log_path=str(artifact_paths["log"]),
                screenshot_path=str(artifact_paths["after_screenshot"]),
                safety_ui_failure=False,
            )

        inputs_exit = run_apply_inputs_command(task_path, dry_run=False, allow_gui_clicks=True)
        if inputs_exit != 0:
            save_window_screenshot(window_win32, artifact_paths["after_screenshot"])
            payload = {
                "timestamp": timestamp,
                "task_path": str(Path(task_path)),
                "task": task_to_payload(task),
                "phase": "apply_inputs",
                "exit_code": inputs_exit,
                "before_screenshot_path": str(artifact_paths["before_screenshot"]),
                "after_screenshot_path": str(artifact_paths["after_screenshot"]),
                "status": "failed",
            }
            write_json(artifact_paths["log"], payload)
            return RunTaskResult(
                exit_code=1,
                status="apply_inputs_failed",
                test_id=task.test_id or "",
                raw_report_path="",
                log_path=str(artifact_paths["log"]),
                screenshot_path=str(artifact_paths["after_screenshot"]),
                safety_ui_failure=False,
            )

        window_win32.set_focus()
        start_button, before_click = capture_button_state(window_win32)
        pre_run_path = artifact_paths["before_screenshot"].with_name(f"run_task_prerun_{timestamp}.png")
        save_window_screenshot(window_win32, pre_run_path)
        run_started_at = time.time()
        start_button.click_input()
        time.sleep(0.5)

        started, start_samples = wait_for_state(window_win32, expected="started", timeout_seconds=min(timeout_seconds, 10))
        finished, finish_samples = wait_for_state(window_win32, expected="finished", timeout_seconds=timeout_seconds)
        save_window_screenshot(window_win32, artifact_paths["after_screenshot"])
        _, after_snapshot = capture_button_state(window_win32)
        test_id = task.test_id or make_test_id(task.name)

        report_missing = False
        raw_report_path = None
        if finished:
            raw_report_path = locate_raw_report(config, started_at=run_started_at)
            if raw_report_path is None:
                report_missing = True
                stored = build_stored_run(
                    test_id=test_id,
                    task=task,
                    parsed_report=None,
                    passed=False,
                    rejection_reason="REPORT_MISSING",
                    raw_report_path="",
                    parsed_report_path="",
                    screenshot_path=str(artifact_paths["after_screenshot"]),
                    run_status="REPORT_MISSING",
                    execution_mode="gui",
                    run_kind=run_kind,
                    parent_candidate_id=parent_candidate_id,
                    split_id=split_id,
                )
                store_run(stored)
                update_leaderboard_csv()
                update_summary_md()
            else:
                parsed_report = parse_report_file(raw_report_path)
                store_parsed_report_json(test_id, parsed_report)
                evaluator = acceptance_evaluator or evaluate_acceptance
                evaluation = coerce_acceptance_evaluation(evaluator(parsed_report, task.acceptance))
                stored = build_stored_run(
                    test_id=test_id,
                    task=task,
                    parsed_report=parsed_report,
                    passed=evaluation.passed,
                    rejection_reason=evaluation.rejection_reason,
                    decision_reason=evaluation.decision_reason,
                    per_rule_results=evaluation.per_rule_results,
                    raw_report_path=str(raw_report_path),
                    parsed_report_path=str(Path(load_config().artifacts_dir).resolve() / "parsed_reports" / f"{test_id}.json"),
                    screenshot_path=str(artifact_paths["after_screenshot"]),
                    run_status=evaluation.status,
                    execution_mode="gui",
                    run_kind=run_kind,
                    parent_candidate_id=parent_candidate_id,
                    split_id=split_id,
                )
                store_run(stored)
                update_leaderboard_csv()
                update_summary_md()

        payload = {
            "timestamp": timestamp,
            "task_path": str(Path(task_path)),
            "task": task_to_payload(task),
            "test_id": test_id if finished else "",
            "timeout_seconds": timeout_seconds,
            "before_button_state": asdict(before_click),
            "start_detected": started,
            "finish_detected": finished,
            "start_samples": start_samples,
            "finish_samples": finish_samples,
            "final_button_state": asdict(after_snapshot),
            "raw_report_path": str(raw_report_path) if finished and raw_report_path is not None else "",
            "result_status": "REPORT_MISSING" if report_missing else ("PARSED" if finished else ""),
            "before_screenshot_path": str(pre_run_path),
            "after_screenshot_path": str(artifact_paths["after_screenshot"]),
            "status": "report_missing" if report_missing else ("ok" if finished else "timeout"),
        }
        write_json(artifact_paths["log"], payload)

        if not finished:
            return RunTaskResult(
                exit_code=1,
                status="timeout",
                test_id=test_id,
                raw_report_path="",
                log_path=str(artifact_paths["log"]),
                screenshot_path=str(artifact_paths["after_screenshot"]),
                safety_ui_failure=True,
            )

        if report_missing:
            return RunTaskResult(
                exit_code=1,
                status="report_missing",
                test_id=test_id,
                raw_report_path="",
                log_path=str(artifact_paths["log"]),
                screenshot_path=str(artifact_paths["after_screenshot"]),
                safety_ui_failure=False,
            )

        return RunTaskResult(
            exit_code=0,
            status="ok",
            test_id=test_id,
            raw_report_path=str(raw_report_path),
            log_path=str(artifact_paths["log"]),
            screenshot_path=str(artifact_paths["after_screenshot"]),
            safety_ui_failure=False,
        )
    except Exception as exc:
        try:
            _, window_win32 = prepare_run_window()
            save_window_screenshot(window_win32, artifact_paths["after_screenshot"])
        except Exception:
            pass
        payload = {
            "timestamp": timestamp,
            "task_path": str(Path(task_path)),
            "timeout_seconds": timeout_seconds,
            "error": str(exc),
            "after_screenshot_path": str(artifact_paths["after_screenshot"]),
            "status": "failed",
        }
        write_json(artifact_paths["log"], payload)
        return RunTaskResult(
            exit_code=1,
            status="failed",
            test_id="",
            raw_report_path="",
            log_path=str(artifact_paths["log"]),
            screenshot_path=str(artifact_paths["after_screenshot"]),
            safety_ui_failure=True,
        )


def run_task_command(
    task_path: str,
    allow_gui_clicks: bool,
    timeout_seconds: int,
    execution_mode: str,
    allow_stop_existing_terminal: bool = False,
    keep_terminal_open: bool = False,
) -> int:
    result = execute_run_task(
        task_path=task_path,
        allow_gui_clicks=allow_gui_clicks,
        timeout_seconds=timeout_seconds,
        execution_mode=execution_mode,
        allow_stop_existing_terminal=allow_stop_existing_terminal,
        keep_terminal_open=keep_terminal_open,
    )
    if result.status == "safety_blocked":
        print("Refusing to run a task without --allow-gui-clicks.")
        return result.exit_code
    if result.status == "PROCESS_FAILED":
        print("run-task failed while launching or waiting for the MT5 CLI process.")
    elif result.status == "FILES_GENERATED":
        print("MT5 files were generated.")
    elif result.status == "REPORT_FOUND":
        print("Backtest finished and the report was found.")
    elif result.status == "PARSE_FAILED":
        print("Backtest report was found, but parsing failed.")
    elif result.status == "apply_tester_settings_failed":
        print("run-task stopped during tester settings application.")
    elif result.status == "apply_inputs_failed":
        print("run-task stopped during input application.")
    elif result.status == "timeout":
        print("Backtest finish could not be confirmed before timeout.")
    elif result.status in {"REPORT_MISSING", "report_missing"}:
        print("Backtest finished, but no raw report was found. Stored as REPORT_MISSING.")
    elif result.status == "TERMINAL_ALREADY_RUNNING":
        print("Configured MT5 terminal is already running. Refusing to launch another CLI instance.")
        print("next command: python -m mt5_research_agent stop-mt5 --confirm")
    elif result.status in {"PASS", "ok"}:
        print(f"task finished for test_id: {result.test_id}")
    elif result.status == "FAIL":
        print(f"task finished for test_id: {result.test_id}, but acceptance rules failed.")
    elif result.status == "FAIL_WITH_MISSING_METRICS":
        print(f"task finished for test_id: {result.test_id}, but required acceptance metrics were missing.")
    else:
        print("run-task failed.")
    if result.screenshot_path:
        print(f"after screenshot: {result.screenshot_path}")
    if result.log_path:
        print(f"log: {result.log_path}")
    return result.exit_code
