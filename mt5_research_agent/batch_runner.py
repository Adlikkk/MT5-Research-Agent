"""BG-4A small batch runner.

Runs a small, bounded batch of pre-generated task JSON files through the
existing single-task execution path. The batch runner never optimizes for
profit, never hides failed attempts, and stops as soon as it sees a severe
infrastructure failure (a launch problem or a safety/UI block) rather than
silently continuing.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from mt5_research_agent.result_store import (
    fetch_run,
    get_results_dir,
    update_leaderboard_csv,
    update_summary_md,
)
from mt5_research_agent.run_task import execute_run_task
from mt5_research_agent.task import load_task


# Statuses that mean the backtest produced a parsed result. A task in one of
# these states is considered "completed" and is skipped unless --rerun is set.
COMPLETED_STATUSES = {"PASS", "FAIL", "FAIL_WITH_MISSING_METRICS"}

# Severe infrastructure failures. These halt the batch instead of letting it
# continue, because every following task would almost certainly fail the same
# way (terminal cannot launch, terminal already running, GUI/safety block).
INFRASTRUCTURE_FAILURE_STATUSES = {"PROCESS_FAILED", "TERMINAL_ALREADY_RUNNING"}


@dataclass(slots=True)
class BatchTaskOutcome:
    test_id: str
    task_path: str
    status: str
    exit_code: int
    passed: bool
    skipped: bool
    halted: bool
    log_path: str


@dataclass(slots=True)
class BatchResult:
    task_dir: str
    execution_mode: str
    dry_run: bool
    total_discovered: int
    eligible: int
    attempted: int
    skipped: int
    passed: int
    failed: int
    halted: bool
    halt_reason: str
    started_at: str
    finished_at: str
    outcomes: list[BatchTaskOutcome] = field(default_factory=list)


def batch_state_path() -> Path:
    return get_results_dir() / "batch_state.json"


def batch_summary_path() -> Path:
    return get_results_dir() / "batch_summary.md"


def discover_batch_tasks(task_dir: str | Path) -> list[tuple[str, Path]]:
    """Return (test_id, path) for every valid task JSON directly in ``task_dir``.

    Files without a ``test_id`` (for example a research ``base_task.json``) and
    files that fail task validation are skipped. Results are sorted by test_id
    for deterministic ordering.
    """

    directory = Path(task_dir)
    if not directory.exists() or not directory.is_dir():
        raise ValueError(f"Task directory does not exist: {directory}")

    discovered: list[tuple[str, Path]] = []
    for path in sorted(directory.glob("*.json")):
        try:
            task = load_task(path)
        except Exception:
            continue
        if not task.test_id:
            continue
        discovered.append((task.test_id, path))
    discovered.sort(key=lambda item: item[0])
    return discovered


def is_task_completed(test_id: str) -> bool:
    row = fetch_run(test_id)
    if row is None:
        return False
    status = str(row.get("effective_run_status") or row.get("run_status") or "")
    return status in COMPLETED_STATUSES


def select_batch_tasks(
    discovered: list[tuple[str, Path]],
    *,
    limit: int | None,
    rerun: bool,
) -> tuple[list[tuple[str, Path]], list[str]]:
    """Split discovered tasks into the ones to run and the ones to skip."""

    to_run: list[tuple[str, Path]] = []
    skipped: list[str] = []
    for test_id, path in discovered:
        if not rerun and is_task_completed(test_id):
            skipped.append(test_id)
            continue
        to_run.append((test_id, path))
        if limit is not None and len(to_run) >= limit:
            break
    return to_run, skipped


def run_batch(
    task_dir: str | Path,
    *,
    limit: int | None = None,
    execution_mode: str = "cli",
    dry_run: bool = False,
    rerun: bool = False,
    allow_gui_clicks: bool = False,
    timeout_seconds: int = 1800,
) -> BatchResult:
    started_at = datetime.now(timezone.utc).isoformat()
    discovered = discover_batch_tasks(task_dir)
    to_run, skipped_ids = select_batch_tasks(discovered, limit=limit, rerun=rerun)

    outcomes: list[BatchTaskOutcome] = []
    for test_id in skipped_ids:
        outcomes.append(
            BatchTaskOutcome(
                test_id=test_id,
                task_path="",
                status="SKIPPED_COMPLETED",
                exit_code=0,
                passed=True,
                skipped=True,
                halted=False,
                log_path="",
            )
        )

    if dry_run:
        for test_id, path in to_run:
            outcomes.append(
                BatchTaskOutcome(
                    test_id=test_id,
                    task_path=str(path),
                    status="DRY_RUN",
                    exit_code=0,
                    passed=False,
                    skipped=False,
                    halted=False,
                    log_path="",
                )
            )
        finished_at = datetime.now(timezone.utc).isoformat()
        result = BatchResult(
            task_dir=str(task_dir),
            execution_mode=execution_mode,
            dry_run=True,
            total_discovered=len(discovered),
            eligible=len(to_run) + len(skipped_ids),
            attempted=0,
            skipped=len(skipped_ids),
            passed=0,
            failed=0,
            halted=False,
            halt_reason="",
            started_at=started_at,
            finished_at=finished_at,
            outcomes=outcomes,
        )
        save_batch_state(result)
        write_batch_summary(result)
        return result

    attempted = 0
    passed = 0
    failed = 0
    halted = False
    halt_reason = ""

    for test_id, path in to_run:
        run_result = execute_run_task(
            str(path),
            allow_gui_clicks=allow_gui_clicks,
            timeout_seconds=timeout_seconds,
            execution_mode=execution_mode,
        )
        attempted += 1
        is_pass = run_result.status in {"PASS", "ok"}
        if is_pass:
            passed += 1
        else:
            failed += 1

        severe = run_result.safety_ui_failure or run_result.status in INFRASTRUCTURE_FAILURE_STATUSES
        outcomes.append(
            BatchTaskOutcome(
                test_id=run_result.test_id or test_id,
                task_path=str(path),
                status=run_result.status,
                exit_code=run_result.exit_code,
                passed=is_pass,
                skipped=False,
                halted=severe,
                log_path=run_result.log_path,
            )
        )

        # Always refresh leaderboard/summary so partial progress is visible
        # even if the batch halts on the next task.
        update_leaderboard_csv()
        update_summary_md()

        if severe:
            halted = True
            halt_reason = (
                "safety/UI failure"
                if run_result.safety_ui_failure
                else f"infrastructure failure ({run_result.status})"
            )
            break

    finished_at = datetime.now(timezone.utc).isoformat()
    result = BatchResult(
        task_dir=str(task_dir),
        execution_mode=execution_mode,
        dry_run=False,
        total_discovered=len(discovered),
        eligible=len(to_run) + len(skipped_ids),
        attempted=attempted,
        skipped=len(skipped_ids),
        passed=passed,
        failed=failed,
        halted=halted,
        halt_reason=halt_reason,
        started_at=started_at,
        finished_at=finished_at,
        outcomes=outcomes,
    )
    save_batch_state(result)
    write_batch_summary(result)
    return result


def save_batch_state(result: BatchResult) -> Path:
    path = batch_state_path()
    path.write_text(json.dumps(asdict(result), indent=2), encoding="utf-8")
    return path


def load_batch_state() -> dict[str, Any] | None:
    path = batch_state_path()
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def write_batch_summary(result: BatchResult) -> Path:
    output_path = batch_summary_path()
    lines = [
        "# MT5 Research Agent Batch Summary",
        "",
        f"- Task directory: {result.task_dir}",
        f"- Execution mode: {result.execution_mode}",
        f"- Dry run: {result.dry_run}",
        f"- Discovered tasks: {result.total_discovered}",
        f"- Attempted: {result.attempted}",
        f"- Skipped (already completed): {result.skipped}",
        f"- Passed: {result.passed}",
        f"- Failed/other: {result.failed}",
        f"- Halted: {result.halted}",
    ]
    if result.halted:
        lines.append(f"- Halt reason: {result.halt_reason}")
    lines.extend(
        [
            f"- Started at: {result.started_at}",
            f"- Finished at: {result.finished_at}",
            "",
            "| Test ID | Status | Pass/Fail | Skipped | Halted | Log |",
            "| --- | --- | --- | --- | --- | --- |",
        ]
    )
    for outcome in result.outcomes:
        lines.append(
            f"| {outcome.test_id} | {outcome.status} | "
            f"{'PASS' if outcome.passed and not outcome.skipped else ('-' if outcome.skipped else 'FAIL')} | "
            f"{'yes' if outcome.skipped else 'no'} | {'yes' if outcome.halted else 'no'} | "
            f"{outcome.log_path or '-'} |"
        )
    output_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return output_path


def run_run_batch_command(
    task_dir: str,
    *,
    limit: int | None,
    execution_mode: str,
    dry_run: bool,
    rerun: bool,
    allow_gui_clicks: bool,
    timeout_seconds: int,
    session: bool = False,
) -> int:
    if execution_mode not in {"cli", "gui"}:
        print(f"Unsupported execution mode: {execution_mode}. Expected 'cli' or 'gui'.")
        return 2
    # Persistent research session mode: reuse the open terminal via GUI rather
    # than restarting MT5 per test. Refuses honestly when it cannot be reliable.
    if session and not dry_run:
        from mt5_research_agent.session import require_active_session_or_explain

        ok, message = require_active_session_or_explain(allow_gui_clicks=allow_gui_clicks)
        print(message)
        if not ok:
            return 2
        execution_mode = "gui"
        allow_gui_clicks = True
    if execution_mode == "gui" and not dry_run and not allow_gui_clicks:
        print("Refusing to run a GUI-mode batch without --allow-gui-clicks.")
        return 2

    try:
        result = run_batch(
            task_dir,
            limit=limit,
            execution_mode=execution_mode,
            dry_run=dry_run,
            rerun=rerun,
            allow_gui_clicks=allow_gui_clicks,
            timeout_seconds=timeout_seconds,
        )
    except Exception as exc:
        print(str(exc))
        return 1

    if dry_run:
        planned = [item for item in result.outcomes if not item.skipped]
        print(f"batch dry run for: {result.task_dir}")
        print(f"discovered tasks: {result.total_discovered}")
        print(f"would skip (already completed): {result.skipped}")
        print(f"would run: {len(planned)}")
        for outcome in planned:
            print(f"  {outcome.test_id} | {outcome.task_path}")
        print(f"batch summary: {batch_summary_path()}")
        return 0

    print(f"batch task dir: {result.task_dir}")
    print(f"attempted: {result.attempted}")
    print(f"skipped (already completed): {result.skipped}")
    print(f"passed: {result.passed}")
    print(f"failed/other: {result.failed}")
    if result.halted:
        print(f"batch halted on {result.halt_reason}")
    print(f"batch summary: {batch_summary_path()}")
    # A halted batch is a non-zero exit; a clean batch with only strategy
    # FAILs is still exit 0 because failed strategies are valid research data.
    return 1 if result.halted else 0


def run_batch_status_command() -> int:
    state = load_batch_state()
    if state is None:
        print("No batch has been run yet.")
        print(f"expected state file: {batch_state_path()}")
        return 1
    print(f"task dir: {state.get('task_dir', '')}")
    print(f"execution mode: {state.get('execution_mode', '')}")
    print(f"dry run: {state.get('dry_run', False)}")
    print(f"discovered tasks: {state.get('total_discovered', 0)}")
    print(f"attempted: {state.get('attempted', 0)}")
    print(f"skipped (already completed): {state.get('skipped', 0)}")
    print(f"passed: {state.get('passed', 0)}")
    print(f"failed/other: {state.get('failed', 0)}")
    print(f"halted: {state.get('halted', False)}")
    if state.get("halted"):
        print(f"halt reason: {state.get('halt_reason', '')}")
    print(f"started at: {state.get('started_at', '')}")
    print(f"finished at: {state.get('finished_at', '')}")
    print(f"batch summary: {batch_summary_path()}")
    return 0
