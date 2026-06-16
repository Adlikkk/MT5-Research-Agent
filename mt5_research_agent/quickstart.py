"""Beginner-friendly quickstart and convenience commands.

These commands lower the barrier for a first-time user: a guided first smoke
test, opening a report or the artifacts folder in the OS file browser, and a
curated examples cheat sheet. None of them place trades or touch live MT5 beyond
the existing, guarded Strategy-Tester smoke path.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any

from mt5_research_agent.background_runner import (
    build_smoke_task_payload,
    configured_artifacts_dir,
    write_generated_task,
)
from mt5_research_agent.config import load_config
from mt5_research_agent.result_store import fetch_run, get_results_dir


EXAMPLES = """MT5 Research Agent - common commands

First-time setup
  mt5-research-agent config-wizard         # detect MT5, write config.json
  mt5-research-agent doctor                # PASS/WARN/FAIL environment check
  mt5-research-agent doctor --json         # same, machine-readable for agents

Your first smoke test (Strategy Tester only)
  mt5-research-agent first-smoke --ea <YourEA> --symbol US30 --timeframe M15
  mt5-research-agent first-smoke --ea <YourEA> --symbol US30 --timeframe M15 --run

Look at results
  mt5-research-agent leaderboard           # refresh results/leaderboard.csv
  mt5-research-agent summarize             # refresh results/summary.md
  mt5-research-agent open-report <test_id> # open a run's report in your browser
  mt5-research-agent open-artifacts        # open the artifacts/results folders

Research loop (request -> plan -> run -> validate -> report)
  mt5-research-agent validate-research-request research_requests/us30_goal.md
  mt5-research-agent plan-from-request     research_requests/us30_goal.md
  mt5-research-agent run-research          research_requests/us30_goal.md
  mt5-research-agent final-report --request research_requests/us30_goal.md

EA Lab (safe-by-default generated EAs)
  mt5-research-agent create-ea-from-prompt research_requests/ea_prompt.md
  mt5-research-agent ea-lab-status <ea_name>

Optional extras
  mt5-research-agent serve-api             # localhost API for the desktop UI
  mt5-research-agent serve-mcp             # safe MCP tools over stdio
  mt5-research-agent ai-status             # optional AI providers (off by default)

Full reference: docs/CLI_REFERENCE.md
Safety: Strategy Tester only. No live trading. No order placement.
"""


def run_examples_command(as_json: bool = False) -> int:
    if as_json:
        requests_dir = Path("research_requests")
        request_files = sorted(str(p) for p in requests_dir.glob("*.md")) if requests_dir.exists() else []
        payload: dict[str, Any] = {
            "ok": True,
            "example_requests": request_files,
            "docs": ["docs/CLI_REFERENCE.md", "docs/GOAL_SEEKING.md", "docs/EA_LAB.md"],
            "safety": "Strategy Tester only. No live trading. No order placement.",
        }
        print(json.dumps(payload, indent=2))
        return 0
    print(EXAMPLES)
    return 0


def _open_path(path: Path) -> bool:
    """Open a file or folder in the OS default handler. Returns True on success."""

    if not path.exists():
        return False
    try:
        if sys.platform == "win32":
            getattr(os, "startfile")(str(path))  # Windows-only; getattr keeps this cross-platform-clean
        elif sys.platform == "darwin":
            os.system(f'open "{path}"')  # noqa: S605 - local path only
        else:
            os.system(f'xdg-open "{path}"')  # noqa: S605 - local path only
        return True
    except OSError:
        return False


def find_report_for_test_id(test_id: str) -> Path | None:
    row = fetch_run(test_id)
    if row is not None:
        raw = str(row.get("raw_report_path", "") or "")
        if raw and Path(raw).exists():
            return Path(raw)
    raw_reports = configured_artifacts_dir() / "raw_reports"
    for suffix in (".htm", ".html", ".xml"):
        candidate = raw_reports / f"{test_id}{suffix}"
        if candidate.exists():
            return candidate
    return None


def run_open_report_command(test_id: str, as_json: bool = False) -> int:
    report = find_report_for_test_id(test_id)
    if report is None:
        message = (
            f"No report found for test_id '{test_id}'. "
            f"Run a backtest first, or check {configured_artifacts_dir() / 'raw_reports'}."
        )
        if as_json:
            print(json.dumps({"ok": False, "error": message}))
        else:
            print(message)
        return 1
    opened = _open_path(report)
    if as_json:
        print(json.dumps({"ok": True, "report_path": str(report), "opened": opened}))
    else:
        print(f"report: {report}")
        print("opened in your default application." if opened else "could not auto-open; open the path above manually.")
    return 0


def run_open_artifacts_command(as_json: bool = False) -> int:
    config = load_config()
    artifacts = Path(config.artifacts_dir).resolve()
    results = get_results_dir()
    artifacts.mkdir(parents=True, exist_ok=True)
    opened_artifacts = _open_path(artifacts)
    opened_results = _open_path(results)
    if as_json:
        print(
            json.dumps(
                {
                    "ok": True,
                    "artifacts_dir": str(artifacts),
                    "results_dir": str(results),
                    "opened_artifacts": opened_artifacts,
                    "opened_results": opened_results,
                }
            )
        )
    else:
        print(f"artifacts: {artifacts}")
        print(f"results:   {results}")
        if not (opened_artifacts or opened_results):
            print("could not auto-open; open the paths above manually.")
    return 0


# A smoke test validates *infrastructure*, not strategy quality, so it uses a
# fast, deterministic model. Real research runs use "Every tick based on real
# ticks" for execution-quality fidelity.
SMOKE_MODEL = "1 minute OHLC"


def run_first_smoke_command(
    *,
    ea: str | None,
    symbol: str,
    timeframe: str,
    period_from: str,
    period_to: str,
    deposit: float,
    run: bool,
    dry_run: bool = False,
    timeout_seconds: int,
    model: str = SMOKE_MODEL,
    as_json: bool = False,
) -> int:
    """Create (and optionally run) a relaxed-acceptance first smoke test.

    Uses a fast, deterministic model (``1 minute OHLC``) because a smoke test is
    infrastructure validation, not a quality/performance run. ``--dry-run`` only
    writes the task and prints the plan; it never launches MT5.
    """

    from mt5_research_agent.background_runner import run_smoke_cli_command

    resolved_ea = ea or "YOUR_COMPILED_EA"
    test_id = "FIRST-SMOKE-0001"
    payload = build_smoke_task_payload(
        test_id=test_id,
        ea=resolved_ea,
        symbol=symbol,
        timeframe=timeframe,
        period_from=period_from,
        period_to=period_to,
        deposit=deposit,
        model=model,
    )
    task_path = write_generated_task(payload)

    if as_json:
        print(
            json.dumps(
                {
                    "ok": True,
                    "test_id": test_id,
                    "task_path": str(task_path),
                    "model": model,
                    "ea": resolved_ea,
                    "will_run": run and not dry_run,
                    "dry_run": dry_run,
                }
            )
        )
    else:
        print("MT5 Research Agent - first smoke test (infrastructure validation)")
        print(f"  EA:        {resolved_ea}{'  (placeholder - pass --ea <YourCompiledEA>)' if ea is None else ''}")
        print(f"  Symbol:    {symbol}  Timeframe: {timeframe}")
        print(f"  Period:    {period_from} -> {period_to}")
        print(f"  Model:     {model}  (fast/deterministic; real research uses every-tick)")
        print(f"  Task file: {task_path}")
        print("")

    if dry_run:
        if not as_json:
            print("Dry run: task written, no MT5 launched. Use --run to launch once doctor shows a valid terminal.")
        return 0

    if not run:
        if not as_json:
            print("Previewing the background CLI command (no MT5 launched).")
            print("Re-run with --run once `doctor` shows a valid terminal64.exe.")
        return run_smoke_cli_command(
            task_path=str(task_path),
            run=False,
            timeout_seconds=timeout_seconds,
            allow_stop_existing_terminal=False,
            keep_terminal_open=False,
        )

    if not as_json:
        print("Launching MT5 Strategy Tester in background CLI mode (one-shot)...")
    return run_smoke_cli_command(
        task_path=str(task_path),
        run=True,
        timeout_seconds=timeout_seconds,
        allow_stop_existing_terminal=False,
        keep_terminal_open=False,
    )
